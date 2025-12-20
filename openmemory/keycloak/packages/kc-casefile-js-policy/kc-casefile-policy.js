// Set to 'true' to enable debug messages in the Keycloak server log.
var ENABLE_KC_POLICY_DEBUG = true;

var debugMessage = function(message) {
  if (ENABLE_KC_POLICY_DEBUG) {
    print('[case-file:acl] ' + message);
  } 
};

debugMessage('------------------------------------ [case-file:acl]: Begin ------------------------------------');

try {
  // Per-scope authorization check
  var isAllowedForScope = function(scopeName, userId, readers, writers, admins) {
    if (!userId) return false;
    // Expects values to be a normalized array, but getAttrValues does that for us
    var containsUser = function(values)  {
      if (!values) return false;
      // Values were normalized on the way in - we have an array of lower-case trimmed strings.
      if (Array.isArray(values)) {
        for (var i = 0; i < values.length; i++) {
          debugMessage('*** Checking ACL item: ' + values[i] + ' against userId: ' + userId);
          if (values[i] == userId) return true;
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
  // Takes in a map or object-like input and returns the value of the given key 
  // as a normalized array of lower-case trimmed and flattened strings.
  var getAttrValues = function(attributes, key) {
    // Normalize final value into a flattened array of lower-case trimmed strings
    var normalizeFinalValue = function(target) {
      if (target == null || target == undefined) return null;      
      // If we have a raw string, split on commas or ';' and then recursively normalize
      if (typeof target == 'string') {
        var parts = target.toString().split(/[,;]/);
        return normalizeFinalValue(parts);
      }
      var normalizedArray = [];
      if (typeof target.iterator == "function") {
        var it = target.iterator();
        while (it.hasNext()) {
          var item = it.next();
          if (item != null && item != undefined) {
            var splitItem = item.toString().split(/[,;]/);
            for(var idx = 0; idx < splitItem.length; idx++) {
              var finalItem = splitItem[idx].toString().toLowerCase().trim();              
              if (finalItem.length > 0) {
                normalizedArray.push(finalItem);
              }
            }
          }
        }
      } else if (Array.isArray(target)) {
        for (var i = 0; i < target.length; i++) {
          var item2 = target[i];
          if (item2 != null && item2 != undefined) {
            var splitItem2 = item2.toString().split(/[,;]/);
            for(var idx2 = 0; idx2 < splitItem2.length; idx2++) {
              var finalItem2 = splitItem2[idx2].toString().toLowerCase().trim();              
              if (finalItem2.length > 0) {
                normalizedArray.push(finalItem2);
              }
            }
          }
        }
      } else {
        // Single value ultra-fallback; should never get here, but lets be safe
        print('WARNING: Attribute value for key "' + key + '" is a single non-iterable/non-array value; normalizing as string.');
        var splitItem3 = target.toString().split(/[,;]/);
        for(var idx3 = 0; idx3 < splitItem3.length; idx3++) {
          var finalItem3 = splitItem3[idx3].toString().toLowerCase().trim();
          if (finalItem3.length > 0) {
            normalizedArray.push(finalItem3);
          }
        }
      }
      return normalizedArray;
    };
    // If not key or not attributes or attributes are not object, return null
    if (!key || !attributes  || typeof attributes !== "object") return null;
    // Fast path: exact key
    if (typeof attributes.get == "function") {
      var direct = attributes.get(key);
      if (direct != null && direct != undefined) return normalizeFinalValue(direct);

      // Case-insensitive scan for java.util.Map
      if (typeof attributes.keySet == "function") {
        var it = attributes.keySet().iterator();
        var normalizedKey = key.toString().toLowerCase().trim();
        while (it.hasNext()) {
          var k = it.next();
          if (k != null && k.toString().toLowerCase().trim() == normalizedKey) {
            return normalizeFinalValue(attributes.get(k));
          }
        }
      }
    } else {
      // JS object fallback
      if (attributes.hasOwnProperty && attributes.hasOwnProperty(key)) return normalizeFinalValue(attributes[key]);

      // Case-insensitive scan for JS object keys (ES5-safe)
      var normalized = key.toString().toLowerCase().trim();
      var keys = Object.keys(attributes);
      for (var i = 0; i < keys.length; i++) {
        var k2 = keys[i];
        if (k2 != null && k2.toString().toLowerCase().trim() == normalized) {
          return normalizeFinalValue(attributes[k2]);
        }
      }
    }
    
    print('WARNING: Attribute key "' + key + '" not found in resource attributes.');
    return null;
  };
  // BEGIN Retrieve contextual information
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
  var permission = $evaluation.getPermission();
  if (permission) {
    var res = permission.getResource ? permission.getResource() : undefined;
    if (res) {
      resource = res;
      var oId = resource.getOwner();
      ownerId = oId ? oId.toString().toLowerCase().trim() : undefined;
    } else {      
      throw new Error('No resource found in permission');
    }
  } else {
    throw new Error('No permission found in evaluation');    
  }
  // BEGIN ACL Evaluation
  debugMessage('Evaluating ACLs');      
  if (ownerId && ownerId == userId) {
    // 1) Owner always allowed
    debugMessage('User is owner: Grant');
    $evaluation.grant();
  } else if (typeof identity.hasRealmRole == 'function' && identity.hasRealmRole("case-file:global-admin")) {
    // 2) Global Admin role always allowed
    debugMessage('User has global admin role: Grant');
    $evaluation.grant();
  } else { 
    // 3) Evaluate scopes against ACLs for this user id
    var scopes = permission.getScopes();
    if (scopes == null || scopes.isEmpty()) {
      throw new Error('No scopes found in permission');
    }
    // Attributes are typically a java.util.Map<String, java.util.Set<String>>
    var attrs = resource.getAttributes ? resource.getAttributes() : null;    
    // So we flatten and normalize them for easier comparisons
    var readers = getAttrValues(attrs, "readers");
    var writers = getAttrValues(attrs, "writers");
    var admins  = getAttrValues(attrs, "admins");
    
    var anyOk = false;
    // Evaluate each requested scope
    debugMessage('Evaluating scopes:');
    var it = scopes.iterator();
    while (it.hasNext()) {
      var s = it.next();
      var scopeName = (s && typeof s.getName == "function") ? s.getName() : s.toString();
      debugMessage('Checking scope "' + scopeName + '"...');
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
      debugMessage('!!!-------- No matching ACLs found: Default deny --------!!!');
      $evaluation.deny();
    }         
  }  
} catch (e) {
  var errMsg = e && e.message ? e.message : e;
  debugMessage('!!!!XxXxXxXxXxXxXxXxXx!!! Error evaluating case ACL: ' + errMsg + ' !!!XxXxXxXxXxXxXxXxXx!!!');
  // Fail safe- deny
  $evaluation.deny();
}
debugMessage('------------------------------------ [case-file:acl]: All Done ------------------------------------');
