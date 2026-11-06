import { Role } from './role.model';

/**
 * Identidad de la cuenta institucional autenticada
 * (`SessionUserSerializer` del backend, plan sección 2.2).
 */
export interface SessionUser {
  id: string;
  institutional_id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
}

/** Respuesta de `POST /api/v1/auth/login/`: sesión emitida. */
export interface LoginResponse {
  access: string;
  user: SessionUser;
  roles: Role[];
}

/**
 * Respuesta de `POST /api/v1/auth/refresh/`: el backend reconstruye la
 * sesión desde la cookie `HttpOnly` y devuelve el token nuevo junto a
 * usuario y roles releídos (plan sección 3.7).
 */
export type RefreshResponse = LoginResponse;

/** Permiso de navegación derivado de un rol activo (`GET /api/v1/auth/me/`). */
export interface NavigationPermission {
  role: Role;
  label: string;
  route: string;
}

/** Respuesta de `GET /api/v1/auth/me/`: identidad, roles y navegación. */
export interface MeResponse {
  user: SessionUser;
  roles: Role[];
  navigation: NavigationPermission[];
}
