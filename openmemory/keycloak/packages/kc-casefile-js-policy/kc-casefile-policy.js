print('[case-file:acl] ' + 'Starting case file ACL evaluation');

// try {
  print('Defining helper functions');

  print('Gathering Context');

  var context = $evaluation.getContext();
  if (!context) {
    print('No context found: Default deny');
    $evaluation.deny();
    exit(0);
  }

  var identity = context.getIdentity();
  if (!identity) {
    print('No identity found in context: Default deny');
    $evaluation.deny();
    exit(0);
  }

  var userId = identity.getId();
  userId = userId ? userId.toString().toLowerCase() : null;
  if (!userId) {
    print('No user identity found: Default deny');
    $evaluation.deny();
    exit(0);
  }
  print('got identity: ' + userId);

  var permission = $evaluation.getPermission();
  if (!permission) {
    print('No permission found: Default deny');
    $evaluation.deny();
    exit(0);
  }
  
  var resource = permission.getResource ? permission.getResource() : null;
  if (!resource) {
    print('No resource found in permission: Default deny');
    $evaluation.deny();
    exit(0);
  }
  print('got resource: ' + resource.getName());

  print('Evaluating ACLs');

  // 1) Owner always allowed
  var ownerId = resource.getOwner();
  if (ownerId && ownerId.toString().toLowerCase() === userId) {
    print('User is owner: Grant');
    $evaluation.grant();
    exit(0);
  }

  // 2) global admin role
  if (identity.hasRealmRole && identity.hasRealmRole("case-file:global-admin")) {
    print('User has global admin role: Grant');
    $evaluation.grant();
    exit(0);
  }
  
// } catch (e) {
//  print('[case-file:acl] ' + 'Error evaluating case ACL: ' + e);
// }

// Default deny
print('Default condition: Deny');
$evaluation.deny();

