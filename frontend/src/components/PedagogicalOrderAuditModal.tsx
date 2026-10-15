import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  ShieldCheck,
  AlertTriangle,
  Layers,
  ArrowRight,
  CheckCircle2,
  RefreshCw,
  Sparkles,
  Info,
} from 'lucide-react';
import { api } from '../services/api';
import type { PedagogicalDeckAuditResult } from '../types';
import { useModalEscape } from '../utils/useModalEscape';

interface PedagogicalOrderAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  deckName: string;
  onAligned?: () => void;
}

export const PedagogicalOrderAuditModal: React.FC<PedagogicalOrderAuditModalProps> = ({
  isOpen,
  onClose,
  deckName,
  onAligned,
}) => {
  const [audit, setAudit] = useState<PedagogicalDeckAuditResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isAligning, setIsAligning] = useState<boolean>(false);
  const [alignmentSuccess, setAlignmentSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useModalEscape(isOpen, onClose);

  const fetchAudit = useCallback(async () => {
    if (!deckName) return;
    setIsLoading(true);
    setError(null);
    setAlignmentSuccess(null);
    try {
      const res = await api.auditPedagogicalDeckOrder(deckName);
      setAudit(res);
    } catch (err: any) {
      setError(err.message || 'Error al obtener la auditoría de orden pedagógico');
    } finally {
      setIsLoading(false);
    }
  }, [deckName]);

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        void fetchAudit();
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isOpen, fetchAudit]);

  const handleAlign = async () => {
    if (!deckName) return;
    setIsAligning(true);
    setError(null);
    try {
      const res = await api.alignPedagogicalDeckOrder(deckName);
      setAlignmentSuccess(res.message);
      // Re-fetch audit to confirm 0 inversions
      const updatedAudit = await api.auditPedagogicalDeckOrder(deckName);
      setAudit(updatedAudit);
      if (onAligned) {
        onAligned();
      }
    } catch (err: any) {
      setError(err.message || 'Error al alinear el mazo en Anki');
    } finally {
      setIsAligning(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div
        className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-3xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                Auditoría de Orden Pedagógico Curricular
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {deckName}
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Verificación matemática de precedencia de conceptos (Nivel 0 ➔ Nivel 1 ➔ Backlog)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {isLoading ? (
            <div className="py-16 flex flex-col items-center justify-center gap-3 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
              <p className="text-sm">Analizando cola de Anki frente al Grafo de Precedencia...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Error en la verificación:</p>
                <p className="text-xs mt-1 text-red-300/90">{error}</p>
                <button
                  onClick={fetchAudit}
                  className="mt-3 px-3 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-xs font-medium text-red-200 transition"
                >
                  Reintentar análisis
                </button>
              </div>
            </div>
          ) : audit ? (
            <>
              {/* Status Banner */}
              <div
                className={`p-4 rounded-xl border flex items-start gap-3.5 ${
                  audit.is_pedagogically_sound
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                    : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                }`}
              >
                {audit.is_pedagogically_sound ? (
                  <CheckCircle2 className="w-6 h-6 flex-shrink-0 text-emerald-400 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-6 h-6 flex-shrink-0 text-amber-400 mt-0.5" />
                )}
                <div>
                  <h4 className="font-semibold text-sm">
                    {audit.is_pedagogically_sound
                      ? 'Secuencia de Aprendizaje 100% Coherente'
                      : `Se detectaron ${audit.inversions_count} anomalías de precedencia cognitiva`}
                  </h4>
                  <p className="text-xs mt-1 text-slate-300 leading-relaxed">
                    {audit.recommendation}
                  </p>
                </div>
              </div>

              {/* Metrics Counters */}
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-700/50">
                  <span className="text-xs text-slate-400 block mb-1">Tarjetas en Anki</span>
                  <span className="text-xl font-bold text-white font-mono">{audit.total_cards}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-700/50">
                  <span className="text-xs text-slate-400 block mb-1">Tarjetas Saneadas</span>
                  <span className="text-xl font-bold text-emerald-400 font-mono">{audit.sanitized_cards}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-700/50">
                  <span className="text-xs text-slate-400 block mb-1">Inversiones de Nivel</span>
                  <span
                    className={`text-xl font-bold font-mono ${
                      audit.inversions_count === 0 ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {audit.inversions_count}
                  </span>
                </div>
              </div>

              {alignmentSuccess && (
                <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2 animate-fade-in">
                  <Sparkles className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>{alignmentSuccess}</span>
                </div>
              )}

              {/* Violations List */}
              {audit.violations.length > 0 ? (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                    <span>Detalle de Inversiones Encontradas</span>
                    <span className="text-slate-500 font-normal">
                      Mostrando {audit.violations.length} de {audit.inversions_count}
                    </span>
                  </h4>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {audit.violations.map((v, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60 text-xs flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 font-mono font-medium">
                              Slot #{v.higher_due} (Nivel {v.higher_depth})
                            </span>
                            <span className="text-slate-200 font-medium truncate max-w-[140px]">
                              {v.higher_concept}
                            </span>
                          </div>
                          <ArrowRight className="w-4 h-4 text-slate-500 flex-shrink-0" />
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 font-mono font-medium">
                              Slot #{v.lower_due} (Nivel {v.lower_depth})
                            </span>
                            <span className="text-slate-200 font-medium truncate max-w-[140px]">
                              {v.lower_concept}
                            </span>
                          </div>
                        </div>
                        <p className="text-slate-400 text-[11px] leading-relaxed pl-1 border-l-2 border-slate-700">
                          {v.reason}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="p-6 rounded-xl bg-slate-800/30 border border-slate-800 text-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                  <h4 className="text-sm font-semibold text-slate-200">
                    Cola de Anki perfectamente sincronizada
                  </h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Los conceptos fundacionales (Nivel 0) se presentarán primero en tus sesiones de estudio,
                    asegurando que construyas el andamiaje mental antes de que aparezcan sus mecanismos o excepciones.
                  </p>
                </div>
              )}

              {/* Informative footer tip */}
              <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-slate-400 text-xs flex items-center gap-2.5">
                <Info className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                <span>
                  Al alinear, las tarjetas saneadas se reubican secuencialmente desde el slot 0 según el orden topológico del DAG. Las tarjetas pendientes quedan en el backlog posterior.
                </span>
              </div>
            </>
          ) : null}
        </div>

        {/* Modal Actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-950/60">
          <button
            onClick={fetchAudit}
            disabled={isLoading || isAligning}
            className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 text-xs font-medium transition flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Actualizar Auditoría
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-300 hover:text-white hover:bg-slate-800 text-xs font-medium transition"
            >
              Cerrar
            </button>
            <button
              onClick={handleAlign}
              disabled={isLoading || isAligning || (audit?.is_pedagogically_sound && !alignmentSuccess)}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white text-xs font-medium shadow-lg shadow-indigo-600/25 transition flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isAligning ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Alineando Cola en Anki...
                </>
              ) : (
                <>
                  <Layers className="w-3.5 h-3.5" />
                  Alinear Cola de Anki con Grafo Curricular
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
