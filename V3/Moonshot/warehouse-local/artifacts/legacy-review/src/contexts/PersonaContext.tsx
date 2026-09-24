import React, { createContext, useContext, useState } from 'react';
import { useLocation } from 'wouter';
import { useQueryClient } from '@tanstack/react-query';

export type Role = 'fleet' | 'supervisor' | 'admin';

const VALID_ROLES: Role[] = ['fleet', 'supervisor', 'admin'];

export function getPersonaHomePath(role: Role): string {
  return role === 'supervisor' ? '/fulfillment' : `/workspace/${role}`;
}

export function getDemoPersona(): Role {
  const stored = localStorage.getItem('demo-persona') as Role;
  if (stored && VALID_ROLES.includes(stored)) {
    return stored;
  }
  return 'supervisor';
}

export function setDemoPersona(role: Role) {
  if (VALID_ROLES.includes(role)) {
    localStorage.setItem('demo-persona', role);
  }
}

interface PersonaContextType {
  role: Role;
  setRole: (role: Role) => void;
}

const PersonaContext = createContext<PersonaContextType | null>(null);

export function PersonaProvider({ children }: { children: React.ReactNode }) {
  const [role, setRoleState] = useState<Role>(getDemoPersona());
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();

  const setRole = (newRole: Role) => {
    if (!VALID_ROLES.includes(newRole)) return;
    setDemoPersona(newRole);
    setRoleState(newRole);
    // Invalidate queries to reload data for the new role
    queryClient.invalidateQueries();
    // Navigate to the role's home
    setLocation(getPersonaHomePath(newRole));
  };

  return (
    <PersonaContext.Provider value={{ role, setRole }}>
      {children}
    </PersonaContext.Provider>
  );
}

export function usePersona() {
  const ctx = useContext(PersonaContext);
  if (!ctx) throw new Error('usePersona must be used within PersonaProvider');
  return ctx;
}
