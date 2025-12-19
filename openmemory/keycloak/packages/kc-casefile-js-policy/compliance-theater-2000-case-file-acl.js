print('[compliance-theater-2000-case-file-acl] Starting ACL evaluation');
var context = $evaluation.getContext();
print('[compliance-theater-2000-case-file-acl] got context');
var identity = context.getIdentity();
print('[compliance-theater-2000-case-file-acl] got identity');
if (identity.hasRealmRole("case-file:global-admin")) {
  print('[compliance-theater-2000-case-file-acl] User has global admin role: Grant');
  $evaluation.grant();
}else{
  print('[compliance-theater-2000-case-file-acl] User does not have global admin role: Continue evaluation')
  $evaluation.deny();
}
print('[compliance-theater-2000-case-file-acl] Completed ACL evaluation');
