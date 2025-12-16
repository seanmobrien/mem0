var context = $evaluation.getContext();
var identity = context.getIdentity();
var userId = identity.getId();

var permission = $evaluation.getPermission();
var resource = permission.getResource();

if (!resource) {
  $evaluation.deny();
  exit(0);
}

// 1. Owner always allowed
var ownerId = resource.getOwner();
if (ownerId && ownerId === userId) {
  $evaluation.grant();
  exit(0);
}

// 2. Optional global admin role
if (identity.hasRealmRole("case-file:global-admin")) {
  $evaluation.grant();
  exit(0);
}

// 3. Evaluate ACL attributes
var scopes = permission.getScopes();
if (scopes == null || scopes.isEmpty()) {
  $evaluation.deny();
  exit(0);
}

var scopeName = scopes.iterator().next().getName();
var attrs = resource.getAttributes();

function hasUser(list, id) {
  if (!list) return false;
  for (var i = 0; i < list.size(); i++) {
    if (list.get(i) === id) return true;
  }
  return false;
}

var readers = attrs.getValue("readers");
var writers = attrs.getValue("writers");
var admins  = attrs.getValue("admins");

if (scopeName === "case-file:read") {
  if (hasUser(readers, userId) ||
      hasUser(writers, userId) ||
      hasUser(admins, userId)) {
    $evaluation.grant();
    exit(0);
  }
}

if (scopeName === "case-file:write") {
  if (hasUser(writers, userId) ||
      hasUser(admins, userId)) {
    $evaluation.grant();
    exit(0);
  }
}

if (scopeName === "case-file:admin") {
  if (hasUser(admins, userId)) {
    $evaluation.grant();
    exit(0);
  }
}

// Default: deny
$evaluation.deny();
