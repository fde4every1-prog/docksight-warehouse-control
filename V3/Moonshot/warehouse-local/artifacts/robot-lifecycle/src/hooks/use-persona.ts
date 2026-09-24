import { useState, useEffect } from 'react';

type Persona = 'fleet' | 'supervisor' | 'admin';

export function usePersona() {
  const [persona, setPersona] = useState<Persona>('fleet');

  useEffect(() => {
    const stored = localStorage.getItem('demo-persona') as Persona | null;
    if (stored && ['fleet', 'supervisor', 'admin'].includes(stored)) {
      setPersona(stored);
    } else {
      localStorage.setItem('demo-persona', 'fleet');
      setPersona('fleet');
    }

    const handleStorage = (e: StorageEvent) => {
      if (e.key === 'demo-persona') {
        const newVal = e.newValue as Persona | null;
        if (newVal && ['fleet', 'supervisor', 'admin'].includes(newVal)) {
          setPersona(newVal);
        }
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const changePersona = (newPersona: Persona) => {
    localStorage.setItem('demo-persona', newPersona);
    setPersona(newPersona);
    // Dispatch event so other components or tabs update immediately
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'demo-persona',
      newValue: newPersona
    }));
  };

  return { persona, setPersona: changePersona };
}