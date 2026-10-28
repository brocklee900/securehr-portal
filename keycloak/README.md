# Keycloak

`securehr-realm.json` is imported on first start: realm, 3 roles, 3 groups->role mappings,
the `securehr-portal` SPA client (PKCE), the `jenkins` client, and a **local fallback user**
(`admin.local`) so work isn't blocked if LDAP federation isn't ready (see risk table).

## Milestone 3: add LDAP federation (Admin console -> securehr realm -> User federation -> Add LDAP)
| Setting | Value |
|---|---|
| Vendor | Other |
| Connection URL | `ldap://ldap:389` |
| Users DN | `ou=people,dc=securehr,dc=local` |
| Username LDAP attribute | `uid` |
| RDN / UUID LDAP attribute | `uid` / `entryUUID` |
| User object classes | `inetOrgPerson` |
| Bind DN | `cn=admin,dc=securehr,dc=local` |
| Bind credential | `$LDAP_ADMIN_PASSWORD` |

Then:
0. **Realm settings -> General -> Unmanaged Attributes = Enabled.** Without this Keycloak 26 drops the `emp_no` attribute and the claim never reaches the token.
1. Mappers -> add `group-ldap-mapper` (groups DN `ou=groups,dc=securehr,dc=local`, group object class `groupOfNames`, membership attr `member`, mode READ_ONLY, preserve inheritance off). Names match the realm groups `hr-admins`, `managers`, `employees`, which carry the realm roles.
2. Mappers -> add `user-attribute-ldap-mapper`: LDAP `employeeNumber` -> user attribute `emp_no` (this feeds the `emp_no` token claim used for manager scoping and RLS).
3. Click **Sync all users**.

## Later milestones
- **MFA (M7):** Authentication -> Required actions -> enable "Configure OTP" as default, or add an OTP step to the browser flow.
- **GitHub (M6):** GitHub Enterprise SAML isn't available on free plans. Use Keycloak as an *identity broker* for GitHub OAuth, or swap to Gitea with an OIDC provider pointed at this realm.
