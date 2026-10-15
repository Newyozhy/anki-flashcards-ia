import React, { useState, useEffect } from 'react';
import {
  Brain,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  X,
  Send,
  HelpCircle,
} from 'lucide-react';
import type {
  SocraticChallengeResponse,
  SocraticEvaluateResponse,
} from '../types';
import { api } from '../services/api';
import { useModalEscape } from '../utils/useModalEscape';

interface SocraticNodeMasteryModalProps {
  isOpen: boolean;
  onClose: () => void;
  deckName: string;
  conceptName: string;
  apiKey?: string;
  onMasteryAchieved?: (conceptName: string) => void;
}

export const SocraticNodeMasteryModal: React.FC<SocraticNodeMasteryModalProps> = ({
  isOpen,
  onClose,
  deckName,
  conceptName,
  apiKey,
  onMasteryAchieved,
}) => {
  const [challenge, setChallenge] = useState<SocraticChallengeResponse | null>(null);
  const [isLoadingChallenge, setIsLoadingChallenge] = useState<boolean>(false);
  const [challengeError, setChallengeError] = useState<string | null>(null);

  const [userResponse, setUserResponse] = useState<string>('');
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [evaluation, setEvaluation] = useState<SocraticEvaluateResponse | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);

  useModalEscape(isOpen, onClose, isEvaluating || isLoadingChallenge);

  // Fetch challenge when modal opens
  useEffect(() => {
    if (!isOpen || !conceptName || !deckName) return;

    let isMounted = true;
    const loadChallenge = async () => {
      setIsLoadingChallenge(true);
      setChallengeError(null);
      setChallenge(null);
      setEvaluation(null);
      setUserResponse('');
      try {
        const res = await api.generateSocraticChallenge(deckName, conceptName, apiKey);
        if (isMounted) {
          setChallenge(res);
        }
      } catch (err: any) {
        if (isMounted) {
          setChallengeError(err.message || 'No se pudo generar el reto socrático para este concepto.');
        }
      } finally {
        if (isMounted) {
          setIsLoadingChallenge(false);
        }
      }
    };

    void loadChallenge();
    return () => {
      isMounted = false;
    };
  }, [isOpen, deckName, conceptName, apiKey]);

  const handleSubmitEvaluation = async () => {
    if (!challenge || !userResponse.trim() || isEvaluating) return;

    setIsEvaluating(true);
    setEvaluationError(null);
    try {
      const result = await api.evaluateSocraticChallenge(
        deckName,
        challenge.concept_id || conceptName,
        {
          concept_id: challenge.concept_id || conceptName,
          challenge_question: challenge.challenge.challenge_question,
          user_answer: userResponse.trim(),
        },
        apiKey
      );
      setEvaluation(result);
      if (result.passed) {
        onMasteryAchieved?.(conceptName);
      }
    } catch (err: any) {
      setEvaluationError(err.message || 'Error al evaluar tu respuesta socrática.');
    } finally {
      setIsEvaluating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="socratic-mastery-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in"
    >
      <div className="relative flex flex-col w-full max-w-3xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-tr from-amber-500/20 to-indigo-500/20 border border-amber-500/30 text-amber-300">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="socratic-mastery-title" className="text-base font-bold text-white">
                  Reto Socrático de Maestría
                </h2>
                <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/30">
                  Red-Teaming
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Eje: <span className="text-indigo-300 font-bold">{challenge?.concept_name || conceptName}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isEvaluating || isLoadingChallenge}
            aria-label="Cerrar modal"
            className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoadingChallenge ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <Loader2 className="h-8 w-8 text-amber-400 animate-spin" />
              <p className="text-sm font-semibold text-slate-300">
                Diseñando escenario socrático adverso (Red-Teaming)...
              </p>
              <p className="text-xs text-slate-500 max-w-md text-center">
                El evaluador IA está construyendo un contraejemplo y caso borde para poner a prueba tus modelos mentales sin darte respuestas obvias.
              </p>
            </div>
          ) : challengeError ? (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 space-y-2">
              <div className="flex items-center gap-2 text-rose-300 text-sm font-semibold">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Error al generar reto</span>
              </div>
              <p className="text-xs text-slate-300">{challengeError}</p>
            </div>
          ) : challenge ? (
            <div className="space-y-5">
              {/* Challenge Scenario Box */}
              {challenge.challenge.scenario_context && (
                <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 space-y-2">
                  <div className="flex items-center gap-2 text-indigo-300 text-xs font-bold uppercase tracking-wider">
                    <Brain className="h-4 w-4" />
                    <span>Escenario de Prueba (Caso Límite)</span>
                  </div>
                  <p className="text-sm text-slate-200 leading-relaxed font-medium">
                    {challenge.challenge.scenario_context}
                  </p>
                </div>
              )}

              {/* Challenge Question */}
              <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 space-y-2">
                <div className="flex items-center gap-2 text-amber-300 text-xs font-bold uppercase tracking-wider">
                  <HelpCircle className="h-4 w-4" />
                  <span>Pregunta Desafiante</span>
                </div>
                <p className="text-sm text-slate-100 font-semibold leading-relaxed">
                  {challenge.challenge.challenge_question}
                </p>
              </div>

              {/* Evaluation Criteria */}
              {challenge.challenge.evaluation_criteria && challenge.challenge.evaluation_criteria.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-amber-400" />
                    Criterios de Evaluación Pedagógica:
                  </span>
                  <ul className="space-y-1.5 pl-4 list-disc text-xs text-slate-400">
                    {challenge.challenge.evaluation_criteria.map((crit: string, idx: number) => (
                      <li key={idx} className="leading-relaxed">
                        {crit}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Evaluation Result Banner (if evaluated) */}
              {evaluation && (
                <div
                  className={`rounded-xl border p-4 space-y-3 transition-all ${
                    evaluation.passed
                      ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200'
                      : 'border-rose-500/40 bg-rose-950/30 text-rose-200'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      {evaluation.passed ? (
                        <>
                          <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                          <span className="text-sm font-bold text-white">
                            ¡Maestría Certificada! (MASTERED)
                          </span>
                        </>
                      ) : (
                        <>
                          <XCircle className="h-5 w-5 text-rose-400" />
                          <span className="text-sm font-bold text-white">
                            Brecha Detectada — Refuerzo Requerido
                          </span>
                        </>
                      )}
                    </div>
                    <span className="rounded-lg bg-slate-900/80 px-2.5 py-1 text-xs font-mono font-bold border border-slate-700">
                      Puntaje: {Math.round(evaluation.score * 100)}% (Corte: 75%)
                    </span>
                  </div>

                  <p className="text-xs text-slate-200 leading-relaxed">
                    {evaluation.feedback}
                  </p>

                  {evaluation.failure_cause && (
                    <div className="text-[11px] text-amber-300 font-medium">
                      Diagnóstico: {evaluation.failure_cause === 'deck_gap' ? 'Brecha en el contenido del mazo' : 'Modelo mental incompleto o fallo de razonamiento'}
                    </div>
                  )}

                  {evaluation.remedy_gap_title && (
                    <p className="text-[11px] text-slate-300 italic pt-1 border-t border-slate-800">
                      💡 Brecha curricular registrada en el DAG: <span className="font-semibold text-amber-200">{evaluation.remedy_gap_title}</span>
                    </p>
                  )}
                </div>
              )}

              {/* User Response Input Area */}
              <div className="space-y-2">
                <label
                  htmlFor="socratic-user-response"
                  className="block text-xs font-semibold text-slate-300"
                >
                  Tu explicación fundamentada desde primeros principios:
                </label>
                <textarea
                  id="socratic-user-response"
                  value={userResponse}
                  onChange={(e) => setUserResponse(e.target.value)}
                  disabled={isEvaluating || (evaluation?.passed ?? false)}
                  rows={5}
                  placeholder="Explica qué ocurre en este escenario, por qué las intuiciones superficiales fallan y qué principio gobierna la solución..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-50 resize-y"
                />
              </div>

              {evaluationError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-950/20 p-3 text-xs text-rose-300">
                  {evaluationError}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-4 bg-slate-950/70">
          <button
            type="button"
            onClick={onClose}
            disabled={isEvaluating}
            className="rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:text-white transition-all cursor-pointer"
          >
            {evaluation?.passed ? 'Cerrar y Continuar' : 'Cancelar'}
          </button>

          {challenge && (!evaluation || !evaluation.passed) && (
            <button
              type="button"
              onClick={handleSubmitEvaluation}
              disabled={isEvaluating || !userResponse.trim()}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 px-5 py-2 text-xs font-bold text-slate-950 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 cursor-pointer shadow-lg shadow-amber-500/20"
            >
              {isEvaluating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Evaluando con IA Socrática...</span>
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  <span>{evaluation ? 'Reintentar Explicación' : 'Validar Mi Modelo Mental'}</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
