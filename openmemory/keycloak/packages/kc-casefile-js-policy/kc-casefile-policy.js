var debugMessage = function(message) {
  // Uncomment the line below to enable debug logging
  print('[case-file:acl] ' + message);
};

debugMessage('------------------------------------ [case-file:acl]: Begin ------------------------------------');

try {
  debugMessage('Defining helper functions');
  // Per-scope authorization check
  var isAllowedForScope = function(scopeName, userId, readers, writers, admins) {
    if (!userId) return false;
    // Works with java.util.Collection / Set / List (iterator) and JS arrays
    var containsUser = function(values)  {
      if (!values) return false;
      // If we have a raw string, split on commas or ';'
      if (typeof values == 'string') {
        // And then send back through to catch the array case
        return containsUser(values.toString().split(/[,;]/));
      }
      if (typeof values.iterator == "function") {
        var it = values.iterator();
        while (it.hasNext()) {
          var checkItem = it.next();
          if (checkItem && checkItem.toString().toLowerCase().trim() == userId) return true;      
        }
        return false;
      }
      if (Array.isArray(values)) {
        for (var i = 0; i < values.length; i++) {
          if (values[i] && values[i].toString().toLowerCase().trim() == userId) return true;
        }
      } else {
        debugMessage('Unsupported ACL attribute type: ' + (typeof values) + ' - (' + values + ')');
      }

      return false;
    };

    var normalizedScope = scopeName ? scopeName.toString().toLowerCase().trim() : "";
    if (normalizedScope == "case-file:read") {
      return (
        containsUser(readers) ||
        containsUser(writers) ||
        containsUser(admins)
      );
    }

    if (normalizedScope == "case-file:write") {
      return (
        containsUser(writers) ||
        containsUser(admins)
      );
    }

    if (normalizedScope == "case-file:admin") {
      return containsUser(admins);
    }

    // Unknown scope -> skip
    return null;
  };
  // Map-like or object-like case-insensitive attribute lookup
  var getAttrValues = function(attributes, key) {
    // If not key or not attributes or attributes are not object, return null
    if (!key || !attributes  || typeof attributes !== "object") return null;
    // Fast path: exact key
    if (typeof attributes.get == "function") {
      var direct = attributes.get(key);
      if (direct != null && direct != undefined) return direct;

      // Case-insensitive scan for java.util.Map
      if (typeof attributes.keySet == "function") {
        var it = attributes.keySet().iterator();
        var normalizedKey = key.toString().toLowerCase().trim();
        while (it.hasNext()) {
          var k = it.next();
          if (k != null && k.toString().toLowerCase().trim() == normalizedKey) {
            return attributes.get(k);
          }
        }
      }
    } else {
      // JS object fallback
      if (attributes.hasOwnProperty && attributes.hasOwnProperty(key)) return attributes[key];

      // Case-insensitive scan for JS object keys (ES5-safe)
      var normalized = key.toString().toLowerCase().trim();
      var keys = Object.keys(attributes);
      for (var i = 0; i < keys.length; i++) {
        var k2 = keys[i];
        if (k2 != null && k2.toString().toLowerCase().trim() == normalized) {
          return attributes[k2];
        }
      }
    }
    
    print('WARNING: Attribute key "' + key + '" not found in resource attributes.');
    return null;
  };
  debugMessage('Gathering Context');

  var context = $evaluation.getContext(),
      identity = undefined,
      userId = undefined,
      resource = undefined,
      ownerId = undefined;
  if (!context) {    
    throw new Error('No context found');
  } 
  identity = context.getIdentity();
  if (identity) {
    var uId = identity.getId();
    userId = uId ? uId.toString().toLowerCase().trim() : null;
    if (!userId || !userId.length) {
      throw new Error('No user id found in identity');
    }
  } else {
    throw new Error('No identity found in context');      
  } 
  debugMessage('got identity: ' + userId);      
  var permission = $evaluation.getPermission();
  if (permission) {
    var res = permission.getResource ? permission.getResource() : undefined;
    if (res) {
      resource = res;
      debugMessage('got resource: ' + resource.getName());
      var oId = resource.getOwner();
      ownerId = oId ? oId.toString().toLowerCase().trim() : undefined;
      debugMessage('got ownerId: ' + (ownerId || 'none'));
    } else {      
      throw new Error('No resource found in permission');
    }
  } else {
    throw new Error('No permission found in evaluation');    
  }

  debugMessage('Evaluating ACLs');      
  if (ownerId && ownerId == userId) {
    // 1) Owner always allowed
    debugMessage('User is owner: Grant');
    $evaluation.grant();
  } else if (typeof identity.hasRealmRole == 'function' && identity.hasRealmRole("case-file:global-admin")) {
    // 2) global admin role    
    debugMessage('User has global admin role: Grant');
    $evaluation.grant();
  } else { 
    // 3) Evaluate ACL attributes
    var scopes = permission.getScopes();
    if (scopes == null || scopes.isEmpty()) {
      throw new Error('No scopes found in permission');
    }
    // Attributes are typically a java.util.Map<String, java.util.Set<String>>
    var attrs = resource.getAttributes ? resource.getAttributes() : null;
    debugMessage("-=-=-=-=-=-=--=-=-=-=--=-=-=-=-=- attrs type=" + (attrs ? attrs.getClass ? attrs.getClass() : typeof attrs : "null") + " -=-=-=-=-=-=--=-=-=-=--=-=-=-=-=-");

    var readers = getAttrValues(attrs, "readers");
    var writers = getAttrValues(attrs, "writers");
    var admins  = getAttrValues(attrs, "admins");
    
    var anyOk = false;

    debugMessage('Evaluating scopes:');
    var it = scopes.iterator();
    while (it.hasNext()) {
      var s = it.next();
      var scopeName = (s && typeof s.getName == "function") ? s.getName() : s.toString();
      var ok = isAllowedForScope(scopeName, userId, readers, writers, admins);

      if (ok == null || ok == undefined) {
        debugMessage('Unknown scope "' + scopeName + '": skipping');
        continue;
      }

      if (!ok) {
        throw new Error('Scope "' + scopeName + '" not allowed');
      }

      debugMessage('Scope "' + scopeName + '" evaluated OK.');
      anyOk = true;
    }

    if (anyOk) {
      debugMessage('All requested case file scopes allowed: Grant');
      $evaluation.grant();    
    } else {
      debugMessage('No matching ACLs found: Default deny');
      $evaluation.deny();
    }         
  }  
} catch (e) {
  var errMsg = e && e.message ? e.message : e;
  debugMessage('Error evaluating case ACL: ' + errMsg);
  // Fail safe- deny
  $evaluation.deny();
}
debugMessage('------------------------------------ [case-file:acl]: All Done ------------------------------------');
