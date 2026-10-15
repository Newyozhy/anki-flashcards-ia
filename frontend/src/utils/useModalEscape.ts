import { useEffect } from 'react';

export function useModalEscape(isOpen: boolean, onClose: () => void, disabled = false): void {
  useEffect(() => {
    if (!isOpen || disabled) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, disabled]);
}
