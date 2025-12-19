print('[case-file:acl] ' + 'Starting case file ACL evaluation');

var debugMessage = function(msg) {
  // When debug messages are needed, uncomment the following line
  print('[case-file:acl] ' + msg);
};



try {
  debugMessage('Defining helper functions');
  // Per-scope authorization check
  var isAllowedForScope = function(scopeName, userId, readers, writers, admins) {
    if (!userId) return false;
    var normalizedId = userId.toString().toLowerCase();
    // Works with java.util.Collection / Set / List (iterator) and JS arrays
    var containsUser = function(values)  {
      if (!values) return false;
      if (typeof values.iterator === "function") {
        var it = values.iterator();
        while (it.hasNext()) {
          var checkItem = it.next();
          if (checkItem && checkItem.toString().toLowerCase() === normalizedId) return true;      
        }
        return false;
      }

      if (Array.isArray(values)) {
        for (var i = 0; i < values.length; i++) {
          if (values[i] && values[i].toString().toLowerCase() === normalizedId) return true;
        }
      }

      return false;
    };

    var normalizedScope = scopeName ? scopeName.toString().toLowerCase() : "";
    if (normalizedScope === "case-file:read") {
      return (
        containsUser(readers) ||
        containsUser(writers) ||
        containsUser(admins)
      );
    }

    if (normalizedScope === "case-file:write") {
      return (
        containsUser(writers) ||
        containsUser(admins)
      );
    }

    if (normalizedScope === "case-file:admin") {
      return containsUser(admins);
    }

    // Unknown scope -> skip
    return null;
  };
  // Map-like or object-like case-insensitive attribute lookup
  var getAttrValues = function(attributes, key) {
    if (!attributes || !key) return null;
    // Fast path: exact key
    if (typeof attributes.get === "function") {
      var direct = attributes.get(key);
      if (direct != null) return direct;

      // Case-insensitive scan for java.util.Map
      if (typeof attributes.keySet === "function") {
        var it = attributes.keySet().iterator();
        var normalizedKey = key.toString().toLowerCase();
        while (it.hasNext()) {
          var k = it.next();
          if (k != null && k.toString().toLowerCase() === normalizedKey) {
            return attributes.get(k);
          }
        }
      }
      return null;
    }

    // JS object fallback
    if (attributes[key]) return attributes[key];

    // Case-insensitive scan for JS object keys (ES5-safe)
    var normalized = key.toString().toLowerCase();
    var keys = Object.keys(attributes);
    for (var i = 0; i < keys.length; i++) {
      var k2 = keys[i];
      if (k2 != null && k2.toString().toLowerCase() === normalized) {
        return attributes[k2];
      }
    }

    return null;
  };
  
  debugMessage('Gathering Context');

  var context = $evaluation.getContext();
  if (!context) {
    debugMessage('No context found: Default deny');
    $evaluation.deny();
    exit(0);
  }

  var identity = context.getIdentity();
  if (!identity) {
    debugMessage('No identity found in context: Default deny');
    $evaluation.deny();
    exit(0);
  }

  var userId = identity.getId();
  userId = userId ? userId.toString().toLowerCase() : null;
  if (!userId) {
    debugMessage('No user identity found: Default deny');
    $evaluation.deny();
    exit(0);
  }
  debugMessage('got identity: ' + userId);

  var permission = $evaluation.getPermission();
  if (!permission) {
    debugMessage('No permission found: Default deny');
    $evaluation.deny();
    exit(0);
  }

  // Nashorn-safe replacement for optional chaining
  var resource = permission.getResource ? permission.getResource() : null;
  if (!resource) {
    debugMessage('No resource found in permission: Default deny');
    $evaluation.deny();
    exit(0);
  }
  debugMessage('got resource: ' + resource.getName());

  debugMessage('Evaluating ACLs');

  // 1) Owner always allowed
  var ownerId = resource.getOwner();
  if (ownerId && ownerId.toString().toLowerCase() === userId) {
    debugMessage('User is owner: Grant');
    $evaluation.grant();
    exit(0);
  }

  // 2) global admin role
  if (identity.hasRealmRole && identity.hasRealmRole("case-file:global-admin")) {
    debugMessage('User has global admin role: Grant');
    $evaluation.grant();
    exit(0);
  }
  
} catch (e) {
  print('[case-file:acl] ' + 'Error evaluating case ACL: ' + e);
}

// Default deny
debugMessage('Default condition: Deny');
$evaluation.deny();
exit(0);
