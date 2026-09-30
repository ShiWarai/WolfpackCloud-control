import Keycloak from 'keycloak-js'

const url = import.meta.env.VITE_KEYCLOAK_URL || ''
const realm = import.meta.env.VITE_KEYCLOAK_REALM || 'wolfpack-control'
const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'wolfpack-control-web'

export const keycloak = new Keycloak({
  url,
  realm,
  clientId,
})

export async function initKeycloak(): Promise<boolean> {
  if (!url) {
    console.warn('VITE_KEYCLOAK_URL is not set')
    return false
  }
  const authenticated = await keycloak.init({
    onLoad: 'check-sso',
    pkceMethod: 'S256',
  })
  return authenticated
}
