var context = $evaluation.getContext();
var identity = context.getIdentity();
var userId = String(identity.getId());

var permission = $evaluation.getPermission();
var resource = permission.getResource();

if (!resource) {
  print('[compliance-theater-2000-case-file-acl] No resource found in permission: Default deny');
  $evaluation.deny();
  exit(0);
}

// 1) Owner always allowed
var ownerId = resource.getOwner();
if (ownerId && String(ownerId) === userId) {
  $evaluation.grant();
  exit(0);
}

// 2) Optional global admin role
if (identity.hasRealmRole("case-file:global-admin")) {
  print('[compliance-theater-2000-case-file-acl] User has global admin role: Grant');
  $evaluation.grant();
  exit(0);
}

// 3) Evaluate ACL attributes
var scopes = permission.getScopes();
if (scopes == null || scopes.isEmpty()) {
  $evaluation.deny();
  exit(0);
}

var scopeName = scopes.iterator().next().getName();

// Attributes are typically a java.util.Map<String, java.util.Set<String>>
var attrs = resource.getAttributes();

// Defensive: handle Map-like and object-like (just in case)
function getAttrValues(attributes, key) {
  if (!attributes) return null;
  if (typeof attributes.get === "function") return attributes.get(key); // java.util.Map
  if (attributes[key]) return attributes[key]; // JS object fallback
  return null;
}

// Works with java.util.Collection / Set / List
function containsUser(values, id) {
  if (!values || !id) return false;
  const normalizedId = String(id).toLowerCase();
  // Java collections usually have iterator()
  if (typeof values.iterator === "function") {
    var it = values.iterator();
    while (it.hasNext()) {
      if (String(it.next()).toLowerCase() === normalizedId) return true;
    }
    return false;
  }

  // If it somehow comes as a JS array
  if (Array.isArray(values)) {
    for (var i = 0; i < values.length; i++) {
      if (String(values[i]).toLowerCase() === normalizedId) return true;
    }
  }

  return false;
}

var readers = getAttrValues(attrs, "readers");
var writers = getAttrValues(attrs, "writers");
var admins  = getAttrValues(attrs, "admins");

if (scopeName === "case-file:read") {
  if (containsUser(readers, userId) ||
      containsUser(writers, userId) ||
      containsUser(admins,  userId)) {
    $evaluation.grant();
    exit(0);
  }
} else if (scopeName === "case-file:write") {
  if (containsUser(writers, userId) ||
      containsUser(admins,  userId)) {
    $evaluation.grant();
    exit(0);
  }
} else if (scopeName === "case-file:admin") {
  if (containsUser(admins, userId)) {
    $evaluation.grant();
    exit(0);
  }
}

// Default deny
print('[compliance-theater-2000-case-file-acl] No matching ACL entry found: Default deny');
$evaluation.deny();
exit(0);
