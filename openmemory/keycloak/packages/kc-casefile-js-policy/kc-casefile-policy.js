function debugMessage(msg) {
  // When debug messages are needed, uncomment the following line
  // print('[case-file:acl] ' + msg);
}

// Works with java.util.Collection / Set / List (iterator) and JS arrays
function containsUser(values, id) {
  if (!values || !id) return false;

  var normalizedId = id.toString().toLowerCase();

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
}

// Per-scope authorization check
function isAllowedForScope(scopeName, userId, readers, writers, admins) {
  if (scopeName === "case-file:read") {
    return (
      containsUser(readers, userId) ||
      containsUser(writers, userId) ||
      containsUser(admins,  userId)
    );
  }

  if (scopeName === "case-file:write") {
    return (
      containsUser(writers, userId) ||
      containsUser(admins,  userId)
    );
  }

  if (scopeName === "case-file:admin") {
    return containsUser(admins, userId);
  }

  // Unknown scope -> skip
  return null;
}

try {
  debugMessage('Defining helper functions');

  // Map-like or object-like case-insensitive attribute lookup
  function getAttrValues(attributes, key) {
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
  }
  
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

  // Getting scopes
  var scopes = permission.getScopes ? permission.getScopes() : null;
  if (scopes == null || scopes.isEmpty()) {
    debugMessage('No scopes found in permission: Default deny');
    $evaluation.deny();
    exit(0);
  }

  var attrs = resource.getAttributes ? resource.getAttributes() : null;

  var readers = getAttrValues(attrs, "readers");
  var writers = getAttrValues(attrs, "writers");
  var admins  = getAttrValues(attrs, "admins");
  
  var anyOk = false;

  var it = scopes.iterator();
  while (it.hasNext()) {
    var s = it.next();
    var scopeName = (s && typeof s.getName === "function") ? s.getName() : s.toString();
    var ok = isAllowedForScope(scopeName, userId, readers, writers, admins);

    if (ok == null || ok == undefined) {
      debugMessage('Unknown scope "' + scopeName + '": skipping');
      continue;
    }

    if (!ok) {
      debugMessage('Scope "' + scopeName + '" not allowed: Deny');
      $evaluation.deny();
      exit(0);
    }

    debugMessage('Scope "' + scopeName + '" evaluated OK.');
    anyOk = true;
  }

  if (anyOk) {
    debugMessage('All requested case file scopes allowed: Grant');
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
