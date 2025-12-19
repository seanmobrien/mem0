print('[case-file:acl] - Starting case file ACL evaluation w/ touch');

try {
  print('Defining helper functions');

  print('Gathering Context');

  var context = $evaluation.getContext(),
      identity = undefined,
      userId = undefined,
      resource = undefined,
      ownerId = undefined;
  if (!context) {
    print('No context found: Default deny');
    $evaluation.deny();    
  } else {
    identity = context.getIdentity();
    if (!identity) {
      print('No identity found in context: Default deny');
      $evaluation.deny();
    } else {
      var uId = identity.getId();
      userId = uId ? uId.toString().toLowerCase() : null;
      if (!userId || !userId.length) {
        print('No user identity found: Default deny');
        $evaluation.deny();
      }
      print('got identity: ' + userId);      
      var permission = $evaluation.getPermission();
      if (!permission) {
        print('No permission found: Default deny');
        $evaluation.deny();        
      } else {
        var res = permission.getResource ? permission.getResource() : undefined;
        if (!res) {
          print('No resource found in permission: Default deny');
          $evaluation.deny();          
        } else {
          resource = res;
          print('got resource: ' + resource.getName());
          var oId = resource.getOwner();
          ownerId = oId ? oId.toString().toLowerCase() : undefined;
        }
      }
    }
  }
  if (!!resource && !!permission && !!identity) {
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
  } else {
    print('Fallthrough - Deny');
    $evaluation.deny();
  }  
} catch (e) {
  print('[case-file:acl] ' + 'Error evaluating case ACL: ' + e);
  // Fail safe- deny
  $evaluation.deny();
}
// Default deny

