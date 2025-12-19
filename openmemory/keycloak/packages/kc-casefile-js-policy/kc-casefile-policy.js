print('------------------------------------ [case-file:acl]: Begin ------------------------------------');

try {
  print('Defining helper functions');

  print('Gathering Context');

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
    userId = uId ? uId.toString().toLowerCase() : null;
    if (!userId || !userId.length) {
      throw new Error('No user id found in identity');
    }
  } else {
    throw new Error('No identity found in context');      
  } 
  print('got identity: ' + userId);      
  var permission = $evaluation.getPermission();
  if (permission) {
    var res = permission.getResource ? permission.getResource() : undefined;
    if (res) {
      resource = res;
      print('got resource: ' + resource.getName());
      var oId = resource.getOwner();
      ownerId = oId ? oId.toString().toLowerCase() : undefined;
      print('got ownerId: ' + (ownerId || 'none'));
    } else {      
      throw new Error('No resource found in permission');
    }
  } else {
    throw new Error('No permission found in evaluation');    
  }

  print('Evaluating ACLs');      
  if (ownerId && ownerId.toString().toLowerCase() === userId) {
    // 1) Owner always allowed
    print('User is owner: Grant');
    $evaluation.grant();
  } else if (identity.hasRealmRole && identity.hasRealmRole("case-file:global-admin")) {
    // 2) global admin role    
    print('User has global admin role: Grant');
    $evaluation.grant();
  } else { 
    print('No matching ACLs found: Default deny');
    $evaluation.deny();
  }         

} catch (e) {
  var errMsg = e && e.message ? e.message : e;
  print('[case-file:acl] ' + 'Error evaluating case ACL: ' + errMsg);
  // Fail safe- deny
  $evaluation.deny();
}
print('------------------------------------ [case-file:acl]: All Done ------------------------------------');
// Default deny

