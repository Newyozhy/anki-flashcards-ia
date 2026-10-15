import React, { useState, useEffect } from 'react';
import {
  Brain,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  ArrowRight,
  RotateCcw,
  Send,
  Lock,
  X,
  FileText,
  UploadCloud,
  Globe,
  Search,
  ChevronDown,
  Loader2,
  Check,
  CheckCheck,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  DeckInterviewForm,
  LearningPlanContract,
  SlotQuestion,
  ExamBlueprint,
  BlueprintAlignmentSummary,
} from '../types';
import { useModalEscape } from '../utils/useModalEscape';

interface DeckInterviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  deckName: string;
  apiKey?: string;
  onContractApproved?: (contract: LearningPlanContract) => void;
}

export const DeckInterviewModal: React.FC<DeckInterviewModalProps> = ({
  isOpen,
  onClose,
  deckName,
  apiKey,
  onContractApproved,
}) => {
  const [step, setStep] = useState<'loading' | 'form' | 'preview' | 'approved'>('loading');
  const [interviewForm, setInterviewForm] = useState<DeckInterviewForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
  const [contract, setContract] = useState<LearningPlanContract | null>(null);
  const [userFeedback, setUserFeedback] = useState<string>('');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Optional Exam Blueprint State
  const [isBlueprintExpanded, setIsBlueprintExpanded] = useState<boolean>(false);
  const [blueprintTab, setBlueprintTab] = useState<'file' | 'text' | 'web'>('file');
  const [blueprintFile, setBlueprintFile] = useState<File | null>(null);
  const [blueprintRawText, setBlueprintRawText] = useState<string>('');
  const [blueprintExamName, setBlueprintExamName] = useState<string>('');
  const [isParsingBlueprint, setIsParsingBlueprint] = useState<boolean>(false);
  const [isAligningBlueprint, setIsAligningBlueprint] = useState<boolean>(false);
  const [parsedBlueprint, setParsedBlueprint] = useState<ExamBlueprint | null>(null);
  const [alignmentSummary, setAlignmentSummary] = useState<BlueprintAlignmentSummary | null>(null);
  const [blueprintError, setBlueprintError] = useState<string | null>(null);

  // Initialize or load existing contract / form
  useEffect(() => {
    if (!isOpen || !deckName) return;

    let isMounted = true;
    const loadState = async () => {
      setStep('loading');
      setError(null);
      try {
        const [contractRes, formRes] = await Promise.allSettled([
          api.getDeckLearningContract(deckName),
          api.generateDeckInterviewForm(deckName, apiKey),
        ]);
        if (!isMounted) return;

        // 1. Check if an approved contract already exists
        const existing = contractRes.status === 'fulfilled' ? contractRes.value : null;
        if (existing && existing.status === 'approved') {
          setContract(existing);
          setStep('approved');
          return;
        }

        // 2. Otherwise use the generated contextual form from DAG
        if (formRes.status === 'fulfilled') {
          const form = formRes.value;
          setInterviewForm(form);
          // Set recommended defaults
          const initialAnswers: Record<string, string> = {};
          form.questions.forEach((q) => {
            const recommended = q.options.find((o) => o.is_recommended) || q.options[0];
            if (recommended) {
              initialAnswers[q.slot_key] = recommended.label;
            }
          });
          setAnswers(initialAnswers);
          setStep('form');
        } else {
          throw formRes.reason;
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Error al inicializar la entrevista pedagógica.');
          setStep('form');
        }
      }
    };

    loadState();
    return () => {
      isMounted = false;
    };
  }, [isOpen, deckName, apiKey]);

  useModalEscape(isOpen, onClose, isProcessing);

  if (!isOpen) return null;

  const handleSelectOption = (slotKey: string, optionLabel: string) => {
    setAnswers((prev) => ({ ...prev, [slotKey]: optionLabel }));
  };

  const handleCustomInputChange = (slotKey: string, val: string) => {
    setCustomInputs((prev) => ({ ...prev, [slotKey]: val }));
    setAnswers((prev) => ({ ...prev, [slotKey]: val }));
  };

  const handleParseBlueprint = async () => {
    setIsParsingBlueprint(true);
    setBlueprintError(null);
    try {
      let bp: ExamBlueprint;
      if (blueprintTab === 'file') {
        if (!blueprintFile) {
          throw new Error('Por favor selecciona un archivo PDF, Markdown o TXT.');
        }
        bp = await api.parseDeckBlueprintFile(deckName, blueprintFile, blueprintExamName.trim() || undefined, apiKey);
      } else if (blueprintTab === 'web') {
        if (!blueprintExamName.trim()) {
          throw new Error('Ingresa el nombre o código de la certificación para buscar en la web.');
        }
        bp = await api.parseDeckBlueprintText(deckName, undefined, blueprintExamName.trim(), true, apiKey);
      } else {
        if (!blueprintRawText.trim()) {
          throw new Error('Por favor pega el texto del temario o syllabus.');
        }
        bp = await api.parseDeckBlueprintText(deckName, blueprintRawText.trim(), blueprintExamName.trim() || undefined, false, apiKey);
      }
      setParsedBlueprint(bp);
    } catch (err: any) {
      setBlueprintError(err.message || 'Error al procesar el temario con IA.');
    } finally {
      setIsParsingBlueprint(false);
    }
  };

  const handleAlignBlueprint = async () => {
    if (!parsedBlueprint) return;
    setIsAligningBlueprint(true);
    setBlueprintError(null);
    try {
      const summary = await api.alignDeckBlueprint(deckName, parsedBlueprint, 0.68, apiKey);
      setAlignmentSummary(summary);

      // Pre-populate / suggest answers aligned with blueprint
      if (summary.blueprint.exam_name) {
        setAnswers((prev) => ({
          ...prev,
          bloom_level: prev.bloom_level || 'Comprensión y Aplicación Práctica (Alineado a Blueprint)',
        }));
      }
    } catch (err: any) {
      setBlueprintError(err.message || 'Error al contrastar temario con el mazo.');
    } finally {
      setIsAligningBlueprint(false);
    }
  };

  const handleSynthesizeContract = async () => {
    setIsProcessing(true);
    setError(null);
    try {
      const result = await api.synthesizeDeckContract(deckName, answers, apiKey);
      if (alignmentSummary) {
        result.blueprint_exam_name = alignmentSummary.exam_name;
        result.blueprint_coverage_pct = alignmentSummary.coverage_percentage;
      }
      setContract(result);
      setStep('preview');
    } catch (err: any) {
      setError(err.message || 'Error al sintetizar el contrato pedagógico.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRefineContract = async () => {
    if (!contract || !userFeedback.trim()) return;
    setIsProcessing(true);
    setError(null);
    try {
      const refined = await api.refineDeckContract(deckName, contract, userFeedback.trim(), apiKey);
      setContract(refined);
      setUserFeedback('');
    } catch (err: any) {
      setError(err.message || 'Error al refinar el contrato.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleApproveContract = async () => {
    if (!contract) return;
    setIsProcessing(true);
    setError(null);
    try {
      const approved = await api.approveDeckContract(deckName, contract);
      setContract(approved);
      setStep('approved');
      if (onContractApproved) {
        onContractApproved(approved);
      }
    } catch (err: any) {
      setError(err.message || 'Error al aprobar y bloquear el contrato.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deck-interview-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto"
    >
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 border border-indigo-500/30 rounded-lg text-indigo-400">
              <Brain className="w-5 h-5" />
            </div>
            <div>
              <h2 id="deck-interview-modal-title" className="text-lg font-bold text-white flex items-center gap-2">
                Fase 2: Entrevista y Plan de Estudio
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  {deckName}
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Llenado contractual de los 4 slots de aprendizaje para guiar el saneamiento y expansión
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar entrevista del mazo"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg flex items-center gap-2 text-rose-300 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Body content based on step */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {step === 'loading' && (
            <div className="py-20 flex flex-col items-center justify-center text-center space-y-4">
              <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-slate-300">
                Analizando el DAG de conceptos de <span className="text-indigo-400">{deckName}</span> y formulando preguntas contextuales...
              </p>
            </div>
          )}

          {step === 'form' && interviewForm && (
            <div className="space-y-6">
              {/* DAG Overview Box */}
              <div className="p-4 bg-slate-800/40 border border-slate-700/50 rounded-xl flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">
                    Ontología Detectada en el Mazo
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">{interviewForm.topic_overview}</p>
                </div>
                <div className="flex gap-4 text-xs">
                  <div className="px-3 py-1.5 bg-slate-800 rounded-lg border border-slate-700">
                    <span className="text-slate-400">Conceptos: </span>
                    <strong className="text-indigo-300">{interviewForm.detected_concepts_count}</strong>
                  </div>
                  <div className="px-3 py-1.5 bg-slate-800 rounded-lg border border-slate-700">
                    <span className="text-slate-400">Brechas Huérfanas: </span>
                    <strong className="text-amber-400">{interviewForm.detected_orphans_count}</strong>
                  </div>
                </div>
              </div>

              {/* Optional Exam Blueprint / Syllabus Collapsible Card */}
              <div className="rounded-xl border border-slate-700/70 bg-slate-800/40 overflow-hidden transition-all">
                <button
                  type="button"
                  onClick={() => setIsBlueprintExpanded(!isBlueprintExpanded)}
                  className="w-full flex items-center justify-between p-3.5 sm:px-4 text-left hover:bg-surface-elevated/80 transition-colors cursor-pointer select-none"
                >
                  <div className="flex items-center gap-2.5 min-w-0 pr-2">
                    <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shrink-0">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-slate-100">
                          Temario Oficial / Exam Blueprint
                        </span>
                        {alignmentSummary ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold">
                            <Check className="h-3 w-3" /> {alignmentSummary.coverage_percentage}% Cobertura ({alignmentSummary.gap_count} brechas agregadas al DAG)
                          </span>
                        ) : parsedBlueprint ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 text-[10px] font-bold">
                            <Sparkles className="h-3 w-3" /> {parsedBlueprint.total_objectives} objetivos listos para contrastar
                          </span>
                        ) : (
                          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400 border border-slate-700">
                            Opcional
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Si preparás un examen de certificación o curso formal, contrastá el mazo contra su syllabus para acordar el alcance y detectar vacíos.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-indigo-300 font-semibold hidden sm:inline">
                      {isBlueprintExpanded ? 'Plegar' : 'Configurar'}
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${
                        isBlueprintExpanded ? 'rotate-180 text-indigo-400' : 'rotate-0'
                      }`}
                    />
                  </div>
                </button>

                {isBlueprintExpanded && (
                  <div className="p-4 border-t border-slate-700/60 bg-slate-900/60 space-y-4 animate-fade-in">
                    {/* Error Banner */}
                    {blueprintError && (
                      <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg flex items-center gap-2 text-rose-300 text-xs">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        <span>{blueprintError}</span>
                      </div>
                    )}

                    {/* Step 1: Input & Parsing */}
                    {!parsedBlueprint ? (
                      <div className="space-y-3">
                        {/* Tab Switcher */}
                        <div className="flex items-center gap-1.5 border-b border-slate-800 pb-2">
                          <button
                            type="button"
                            onClick={() => setBlueprintTab('file')}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                              blueprintTab === 'file'
                                ? 'bg-indigo-600 text-white shadow-xs'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                            }`}
                          >
                            <UploadCloud className="h-3.5 w-3.5" />
                            <span>Subir Archivo (PDF / TXT / MD)</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setBlueprintTab('text')}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                              blueprintTab === 'text'
                                ? 'bg-indigo-600 text-white shadow-xs'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                            }`}
                          >
                            <FileText className="h-3.5 w-3.5" />
                            <span>Pegar Texto</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setBlueprintTab('web')}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                              blueprintTab === 'web'
                                ? 'bg-indigo-600 text-white shadow-xs'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                            }`}
                          >
                            <Globe className="h-3.5 w-3.5" />
                            <span>Buscar en la Web</span>
                          </button>
                        </div>

                        {/* Exam Name Input (Optional in file/text, required in web) */}
                        <div className="space-y-1">
                          <label htmlFor="blueprint-exam-name" className="text-[11px] font-bold text-slate-300">
                            Nombre o Código del Examen {blueprintTab === 'web' ? '(Obligatorio)' : '(Opcional)'}
                          </label>
                          <input
                            id="blueprint-exam-name"
                            type="text"
                            placeholder="Ej: Oracle Cloud Infrastructure 2024 Foundations Associate (1Z0-1085-24)"
                            value={blueprintExamName}
                            onChange={(e) => setBlueprintExamName(e.target.value)}
                            className="w-full px-3 py-2 bg-slate-950/80 border border-slate-700/80 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                          />
                        </div>

                        {/* File Upload Mode */}
                        {blueprintTab === 'file' && (
                          <div className="space-y-1.5">
                            <label htmlFor="blueprint-file-input" className="text-[11px] font-bold text-slate-300">
                              Archivo del Temario Oficial (PDF, Markdown o TXT)
                            </label>
                            <div className="flex items-center gap-3">
                              <input
                                id="blueprint-file-input"
                                type="file"
                                accept=".pdf,.txt,.md"
                                onChange={(e) => {
                                  const f = e.target.files?.[0] || null;
                                  setBlueprintFile(f);
                                }}
                                className="block w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 file:cursor-pointer cursor-pointer"
                              />
                            </div>
                            {blueprintFile && (
                              <p className="text-[11px] text-emerald-400 flex items-center gap-1 font-mono">
                                <Check className="h-3 w-3" /> Archivo cargado: {blueprintFile.name} ({(blueprintFile.size / 1024).toFixed(1)} KB)
                              </p>
                            )}
                          </div>
                        )}

                        {/* Text Mode */}
                        {blueprintTab === 'text' && (
                          <div className="space-y-1.5">
                            <label htmlFor="blueprint-raw-text" className="text-[11px] font-bold text-slate-300">
                              Contenido del Temario / Blueprint
                            </label>
                            <textarea
                              id="blueprint-raw-text"
                              rows={5}
                              placeholder="Pega aquí los dominios, temas y subtemas del temario oficial..."
                              value={blueprintRawText}
                              onChange={(e) => setBlueprintRawText(e.target.value)}
                              className="w-full p-2.5 bg-slate-950/80 border border-slate-700/80 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-sans"
                            />
                          </div>
                        )}

                        {/* Web Mode description */}
                        {blueprintTab === 'web' && (
                          <div className="rounded-lg bg-indigo-950/30 border border-indigo-900/40 p-3 text-xs text-indigo-300 space-y-1">
                            <p className="font-semibold flex items-center gap-1.5 text-indigo-200">
                              <Globe className="h-3.5 w-3.5" />
                              Búsqueda asistida en la Web
                            </p>
                            <p className="text-[11px] text-indigo-300/80 leading-relaxed">
                              El agente buscará en internet el temario oficial más reciente para el examen especificado y extraerá su estructura jerárquica para tu revisión antes de confirmarlo.
                            </p>
                          </div>
                        )}

                        {/* Parse Action Button */}
                        <div className="pt-1 flex justify-end">
                          <button
                            type="button"
                            disabled={isParsingBlueprint}
                            onClick={handleParseBlueprint}
                            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-indigo-600/20 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                          >
                            {isParsingBlueprint ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Sparkles className="h-3.5 w-3.5" />
                            )}
                            <span>{isParsingBlueprint ? 'Estructurando Temario...' : 'Analizar y Estructurar con IA'}</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* Step 2: Review Structured Blueprint & Contrast */
                      <div className="space-y-4">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">
                              Blueprint Estructurado ({parsedBlueprint.source_type})
                            </span>
                            <h4 className="text-sm font-bold text-white">
                              {parsedBlueprint.exam_name}
                            </h4>
                            {parsedBlueprint.provider && (
                              <span className="text-[11px] text-slate-400 font-medium">
                                Proveedor: {parsedBlueprint.provider}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-xs">
                            <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                              {parsedBlueprint.domains.length} Dominios
                            </span>
                            <span className="px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-300 border border-indigo-800/60 font-mono font-bold">
                              {parsedBlueprint.total_objectives} Objetivos
                            </span>
                          </div>
                        </div>

                        {/* Domains & Objectives Preview */}
                        <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                          {parsedBlueprint.domains.map((dom) => (
                            <div
                              key={dom.domain_id}
                              className="rounded-lg border border-slate-800 bg-slate-950/50 p-2.5 space-y-1.5 text-xs"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-slate-200">
                                  {dom.domain_id}: {dom.name}
                                </span>
                                {dom.weight_pct !== null && dom.weight_pct !== undefined && (
                                  <span className="text-[10px] font-bold text-indigo-300 bg-indigo-950/50 px-2 py-0.5 rounded border border-indigo-900/40">
                                    {dom.weight_pct}% del examen
                                  </span>
                                )}
                              </div>
                              <ul className="list-disc list-inside space-y-0.5 text-[11px] text-slate-400 pl-1">
                                {dom.objectives.map((obj) => (
                                  <li key={obj.objective_id} className="truncate">
                                    <strong className="text-slate-300 font-mono">{obj.objective_id}</strong> {obj.title}
                                    {obj.coverage_status === 'covered' && (
                                      <span className="ml-2 text-emerald-400 text-[10px]">✓ Cubierto</span>
                                    )}
                                    {obj.coverage_status === 'gap' && (
                                      <span className="ml-2 text-rose-400 text-[10px]">⚠ Brecha</span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>

                        {/* Alignment Actions */}
                        {!alignmentSummary ? (
                          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                            <button
                              type="button"
                              onClick={() => {
                                setParsedBlueprint(null);
                                setAlignmentSummary(null);
                              }}
                              className="text-xs text-slate-400 hover:text-white transition-colors cursor-pointer"
                            >
                              ← Cambiar temario
                            </button>
                            <button
                              type="button"
                              disabled={isAligningBlueprint}
                              onClick={handleAlignBlueprint}
                              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-emerald-600/20 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                            >
                              {isAligningBlueprint ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Search className="h-3.5 w-3.5" />
                              )}
                              <span>
                                {isAligningBlueprint
                                  ? 'Contrastando con Mazo...'
                                  : 'Contrastar con Mazo y Detectar Brechas'}
                              </span>
                            </button>
                          </div>
                        ) : (
                          /* Alignment Completed Box */
                          <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-3.5 space-y-2 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-emerald-300 flex items-center gap-1.5">
                                <CheckCheck className="h-4 w-4" />
                                Contraste Completado con Éxito
                              </span>
                              <span className="text-emerald-300 font-mono font-bold">
                                {alignmentSummary.coverage_percentage}% de Cobertura
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-2 text-center pt-1">
                              <div className="rounded-lg bg-slate-900/80 p-2 border border-slate-800">
                                <span className="text-[10px] text-slate-400 block">Total Objetivos</span>
                                <strong className="text-white text-xs">{alignmentSummary.total_objectives}</strong>
                              </div>
                              <div className="rounded-lg bg-emerald-950/40 p-2 border border-emerald-800/40">
                                <span className="text-[10px] text-emerald-300 block">Cubiertos</span>
                                <strong className="text-emerald-400 text-xs">{alignmentSummary.covered_count}</strong>
                              </div>
                              <div className="rounded-lg bg-rose-950/40 p-2 border border-rose-800/40">
                                <span className="text-[10px] text-rose-300 block">Brechas en DAG</span>
                                <strong className="text-rose-400 text-xs">{alignmentSummary.gap_count}</strong>
                              </div>
                            </div>
                            <p className="text-[11px] text-slate-300 leading-relaxed pt-1">
                              Se han inyectado automáticamente <strong>{alignmentSummary.created_gaps_count} brechas curriculares</strong> en el Grafo DAG (Fase 1) y en la cola de Expansión Topológica (Fase 4). Los acuerdos del formulario abajo se han pre-configurado para alinearse a este examen.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 4 Slot Questions */}
              <div className="space-y-6">
                {interviewForm.questions.map((q: SlotQuestion, qIdx: number) => {
                  const currentAnswer = answers[q.slot_key] || '';
                  return (
                    <div
                      key={q.slot_key}
                      className="p-5 bg-slate-800/60 border border-slate-700/60 rounded-xl space-y-3"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase tracking-wide">
                              Slot {qIdx + 1}: {q.slot_key.replace('_', ' ')}
                            </span>
                          </div>
                          <h4 className="text-sm font-bold text-white mt-1">{q.title}</h4>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {q.contextual_explanation}
                          </p>
                        </div>
                      </div>

                      {/* Options */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                        {q.options.map((opt) => {
                          const isSelected = currentAnswer === opt.label;
                          return (
                            <button
                              key={opt.id}
                              type="button"
                              onClick={() => handleSelectOption(q.slot_key, opt.label)}
                              className={`p-3.5 rounded-lg border text-left transition-all flex flex-col justify-between ${
                                isSelected
                                  ? 'bg-indigo-600/15 border-indigo-500 text-white shadow-sm'
                                  : 'bg-slate-900/50 border-slate-700/70 text-slate-300 hover:border-slate-600'
                              }`}
                            >
                              <div className="flex items-center justify-between w-full">
                                <span className="text-xs font-semibold text-white">
                                  {opt.label}
                                </span>
                                {opt.is_recommended && (
                                  <span className="px-1.5 py-0.5 text-[10px] font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded">
                                    Recomendado
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                                {opt.description}
                              </p>
                            </button>
                          );
                        })}
                      </div>

                      {/* Custom Input */}
                      {q.custom_input_allowed && (
                        <div className="pt-2">
                          <input
                            type="text"
                            aria-label={`Instrucción personalizada para ${q.title}`}
                            placeholder="O escribe una instrucción o ajuste específico para este slot..."
                            value={customInputs[q.slot_key] || ''}
                            onChange={(e) => handleCustomInputChange(q.slot_key, e.target.value)}
                            className="w-full px-3 py-2 bg-slate-900/80 border border-slate-700/60 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {step === 'preview' && contract && (
            <div className="space-y-6">
              {/* Preview Banner */}
              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Sparkles className="w-5 h-5 text-emerald-400" />
                  <div>
                    <h3 className="text-sm font-bold text-white">
                      Vista Previa del Contrato Pedagógico (Borrador v{contract.version})
                    </h3>
                    <p className="text-xs text-slate-300">
                      Revisa los acuerdos consolidados. Si deseas modificar algo, puedes afinarlo con lenguaje natural abajo.
                    </p>
                  </div>
                </div>
                <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Pendiente de Aprobación
                </span>
              </div>

              {/* Structured Clauses Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-slate-800/50 border border-slate-700/60 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Nivel Cognitivo (Bloom)
                  </span>
                  <p className="text-sm font-semibold text-indigo-300 mt-1">{contract.bloom_level}</p>
                </div>
                <div className="p-4 bg-slate-800/50 border border-slate-700/60 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Estrategia para Brechas
                  </span>
                  <p className="text-sm font-semibold text-emerald-300 mt-1">
                    {contract.gap_strategy === 'fill_all_anchors'
                      ? 'Crear tarjetas base atómicas'
                      : contract.gap_strategy === 'assume_prerequisites'
                      ? 'Asumir prerrequisitos como aprendidos'
                      : contract.gap_strategy}
                  </p>
                </div>
                <div className="p-4 bg-slate-800/50 border border-slate-700/60 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Frontera de Exclusión
                  </span>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {contract.exclusion_boundary && contract.exclusion_boundary.length > 0 ? (
                      contract.exclusion_boundary.map((ex, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 text-xs bg-rose-500/10 text-rose-300 border border-rose-500/20 rounded"
                        >
                          ✕ {ex}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-400">Sin exclusiones declaradas</span>
                    )}
                  </div>
                </div>
                <div className="p-4 bg-slate-800/50 border border-slate-700/60 rounded-xl">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Profundidad Operativa
                  </span>
                  <p className="text-sm font-semibold text-slate-200 mt-1">
                    {contract.operational_depth}
                  </p>
                </div>
              </div>

              {/* Executive Summary Markdown */}
              <div className="p-4 bg-slate-800/40 border border-slate-700/40 rounded-xl">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  Resumen Ejecutivo del Acuerdo
                </span>
                <div className="mt-2 text-xs text-slate-200 whitespace-pre-wrap leading-relaxed font-sans">
                  {contract.raw_summary}
                </div>
              </div>

              {/* Natural Language Refinement Input */}
              <div className="p-4 bg-slate-800/70 border border-slate-700/80 rounded-xl space-y-2">
                <label htmlFor="contract-refinement-input" className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  ¿Deseas cambiar o aclarar algo del plan? Negócialo con el agente:
                </label>
                <div className="flex gap-2">
                  <input
                    id="contract-refinement-input"
                    type="text"
                    placeholder="Ej. 'Excluye también comandos de OCI CLI y enfócate en troubleshooting'..."
                    value={userFeedback}
                    onChange={(e) => setUserFeedback(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !isProcessing) handleRefineContract();
                    }}
                    className="flex-1 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                  <button
                    type="button"
                    onClick={handleRefineContract}
                    disabled={isProcessing || !userFeedback.trim()}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
                  >
                    <Send className="w-3.5 h-3.5" />
                    Ajustar
                  </button>
                </div>
              </div>
            </div>
          )}

          {step === 'approved' && contract && (
            <div className="py-12 flex flex-col items-center justify-center text-center space-y-4">
              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-full text-emerald-400">
                <CheckCircle2 className="w-12 h-12" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">
                  Contrato Pedagógico Aprobado y Bloqueado
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                  El estándar de aprendizaje para <strong className="text-indigo-400">{deckName}</strong> quedó fijado en el sistema. Ahora podemos proceder con la Fase 3: Saneamiento Quirúrgico de tarjetas.
                </p>
              </div>

              <div className="p-4 bg-slate-800/60 border border-slate-700/60 rounded-xl max-w-lg w-full text-left text-xs space-y-2 mt-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Nivel Bloom:</span>
                  <span className="font-semibold text-slate-200">{contract.bloom_level}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Tratamiento de Brechas:</span>
                  <span className="font-semibold text-emerald-400">{contract.gap_strategy}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Versión Final:</span>
                  <span className="font-semibold text-slate-200">v{contract.version}</span>
                </div>
                {contract.approved_at && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Fecha de Bloqueo:</span>
                    <span className="text-slate-300">{new Date(contract.approved_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-800/80 border-t border-slate-700/60 flex items-center justify-between">
          {step === 'form' && (
            <>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSynthesizeContract}
                disabled={isProcessing}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition-all"
              >
                {isProcessing ? 'Sintetizando...' : 'Sintetizar Contrato de Aprendizaje'}
                <ArrowRight className="w-4 h-4" />
              </button>
            </>
          )}

          {step === 'preview' && (
            <>
              <button
                type="button"
                onClick={() => setStep('form')}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Volver a Modificar Respuestas
              </button>
              <button
                type="button"
                onClick={handleApproveContract}
                disabled={isProcessing}
                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg flex items-center gap-2 shadow-lg shadow-emerald-600/20 transition-all"
              >
                <Lock className="w-4 h-4" />
                {isProcessing ? 'Aprobando...' : 'Aprobar y Bloquear Contrato'}
              </button>
            </>
          )}

          {step === 'approved' && (
            <div className="w-full flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-lg transition-colors"
              >
                Listo para Fase 3 (Saneamiento)
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
