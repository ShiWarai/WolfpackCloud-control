export type UserRole = 'user' | 'admin'
export type RobotStatus = 'pending' | 'active' | 'inactive' | 'error'
export type Architecture = 'arm64' | 'amd64' | 'armhf'
export type PairCodeStatus = 'pending' | 'confirmed' | 'expired'

export interface User {
  id: number
  email: string
  name: string
  role: UserRole
  is_active: boolean
  keycloak_sub?: string | null
  created_at: string
}

export interface Robot {
  id: number
  name: string
  hostname: string
  ip_address: string | null
  architecture: Architecture
  description: string | null
  status: RobotStatus
  owner_id: number | null
  network_id?: number | null
  created_at: string
  updated_at: string
  last_seen_at: string | null
}

export interface RobotDetail extends Robot {
  influxdb_token: string | null
}

export interface RobotListResponse {
  robots: Robot[]
  total: number
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface PairCodeInfo {
  code: string
  status: PairCodeStatus
  created_at: string
  expires_at: string
  robot: Robot | null
}

export interface PairConfirmResponse {
  robot_id: number
  status: RobotStatus
  influxdb_token: string
  message: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
}

export interface RobotUpdate {
  name?: string
  description?: string
  status?: RobotStatus
  network_id?: number | null
}
