import React, { useRef } from 'react';
import {
  FileText,
  Image as ImageIcon,
  Upload,
  X,
  Sparkles,
  BookOpen,
  Layers,
  Paperclip,
} from 'lucide-react';
import type { DeckNoteRecord } from '../types';
import { stripHtmlAndDecode } from '../utils/clozeParser';

export type InputMaterialMode = 'text' | 'file' | 'anki';

interface ContentDropzoneProps {
  inputMode: InputMaterialMode;
  setInputMode: (mode: InputMaterialMode) => void;
  rawText: string;
  setRawText: (text: string) => void;
  selectedFile: File | null;
  setSelectedFile: (file: File | null) => void;
  filePreviewUrl: string | null;
  // Accompanying image for "Texto / Apuntes"
  textAttachedImage?: File | null;
  setTextAttachedImage?: (file: File | null) => void;
  textAttachedImageUrl?: string | null;
  // Selected Anki Card for "Tarjetas de Anki"
  selectedAnkiCard?: DeckNoteRecord | null;
  onOpenAnkiCardPicker?: () => void;
  onClearAnkiCard?: () => void;
  isAnkiConnected?: boolean;
}

const SAMPLE_TEXT = `El sistema nervioso central (SNC) está compuesto por el encéfalo y la médula espinal.
Su unidad funcional fundamental es la neurona, encargada de la transmisión sináptica de potenciales de acción a través de neurotransmisores como el glutamato (principal excitador) y el GABA (principal inhibidor).
La mielinización, producida por los oligodendrocitos en el SNC y las células de Schwann en el sistema nervioso periférico, incrementa drásticamente la velocidad de conducción mediante el mecanismo de conducción saltatoria a lo largo de los nódulos de Ranvier.`;

export const ContentDropzone: React.FC<ContentDropzoneProps> = ({
  inputMode,
  setInputMode,
  rawText,
  setRawText,
  selectedFile,
  setSelectedFile,
  filePreviewUrl,
  textAttachedImage,
  setTextAttachedImage,
  textAttachedImageUrl,
  selectedAnkiCard,
  onOpenAnkiCardPicker,
  onClearAnkiCard,
  isAnkiConnected = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textImageInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (inputMode === 'text') {
        if (file.type.startsWith('image/') && setTextAttachedImage) {
          setTextAttachedImage(file);
        }
      } else if (isValidFile(file)) {
        setInputMode('file');
        setSelectedFile(file);
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (isValidFile(file)) {
        setSelectedFile(file);
      }
    }
  };

  const handleTextareaPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items || !setTextAttachedImage) return;

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          setTextAttachedImage(file);
          break;
        }
      }
    }
  };

  const isValidFile = (file: File) => {
    const validTypes = [
      'application/pdf',
      'image/png',
      'image/jpeg',
      'image/jpg',
      'image/webp',
    ];
    return validTypes.includes(file.type);
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
      {/* Mode Switcher Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800/80 pb-4 mb-4 gap-3">
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setInputMode('anki')}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all ${
              inputMode === 'anki'
                ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Layers className="h-4 w-4" />
            <span>Tarjeta de Anki</span>
            {selectedAnkiCard && (
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>

          <button
            type="button"
            onClick={() => setInputMode('text')}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all ${
              inputMode === 'text'
                ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <FileText className="h-4 w-4" />
            Texto / Apuntes
          </button>

          <button
            type="button"
            onClick={() => setInputMode('file')}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all ${
              inputMode === 'file'
                ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <ImageIcon className="h-4 w-4" />
            Subir Documento o Imagen
          </button>
        </div>

        {inputMode === 'text' && (
          <button
            type="button"
            onClick={() => setRawText(SAMPLE_TEXT)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 transition-colors self-start sm:self-auto"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Cargar ejemplo
          </button>
        )}
      </div>

      {/* Input Area */}
      {inputMode === 'text' ? (
        <div className="space-y-3" onDragOver={handleDragOver} onDrop={handleDrop}>
          <div className="relative">
            <textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              onPaste={handleTextareaPaste}
              aria-label="Texto o apuntes educativos"
              placeholder="Pegá acá el texto de tu clase, resumen, capítulo de libro o apuntes educativos... Podés presionar Ctrl+V con una imagen en el portapapeles para adjuntarla como apoyo visual."
              rows={7}
              className="w-full resize-y rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500/60 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all leading-relaxed"
            />
          </div>

          {/* Attached image preview card if user pasted or attached an image */}
          {textAttachedImage && (
            <div className="flex items-center justify-between rounded-xl border border-indigo-500/30 bg-indigo-950/30 p-2.5 animate-fade-in">
              <div className="flex items-center gap-3 overflow-hidden">
                {textAttachedImageUrl ? (
                  <img
                    src={textAttachedImageUrl}
                    alt="Preview de apoyo"
                    className="h-12 w-12 rounded-lg object-cover border border-slate-700 shrink-0"
                  />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-600/30 text-indigo-300 shrink-0">
                    <ImageIcon className="h-6 w-6" />
                  </div>
                )}
                <div className="truncate">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-white truncate">
                      {textAttachedImage.name}
                    </span>
                    <span className="rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-1.5 py-0.2 text-[9px] font-bold">
                      Imagen de apoyo
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {(textAttachedImage.size / 1024).toFixed(0)} KB • La IA analizará este gráfico junto con tus apuntes
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setTextAttachedImage && setTextAttachedImage(null)}
                aria-label="Quitar imagen adjunta"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
                title="Quitar imagen adjunta"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* Text footer with image attach trigger */}
          <div className="flex items-center justify-between text-xs text-slate-400 flex-wrap gap-2 pt-1">
            <div className="flex items-center gap-3">
              <span>Soporta fórmulas en LaTeX ($...$)</span>
              <button
                type="button"
                onClick={() => textImageInputRef.current?.click()}
                className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                <Paperclip className="h-3.5 w-3.5" />
                <span>{textAttachedImage ? 'Reemplazar imagen de apoyo' : 'Adjuntar o pegar imagen (Ctrl+V)'}</span>
              </button>
              <input
                ref={textImageInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp"
                aria-label="Adjuntar imagen de apoyo"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0] && setTextAttachedImage) {
                    setTextAttachedImage(e.target.files[0]);
                  }
                }}
                className="hidden"
              />
            </div>
            <span>{rawText.length} caracteres</span>
          </div>
        </div>
      ) : inputMode === 'file' ? (
        <div
          role="button"
          tabIndex={0}
          aria-label="Subir documento PDF o imagen"
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className="relative flex min-h-[190px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700/70 bg-slate-950/40 p-6 text-center hover:border-indigo-500/50 hover:bg-slate-900/40 transition-all cursor-pointer group"
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,image/png,image/jpeg,image/jpg,image/webp"
            aria-label="Subir archivo PDF o imagen"
            onChange={handleFileChange}
            className="hidden"
          />

          {selectedFile ? (
            <div
              className="flex w-full max-w-md items-center justify-between rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-3 text-left"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 overflow-hidden">
                {filePreviewUrl ? (
                  <img
                    src={filePreviewUrl}
                    alt="Preview"
                    className="h-12 w-12 rounded-lg object-cover border border-slate-700"
                  />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-indigo-600/30 text-indigo-300">
                    <BookOpen className="h-6 w-6" />
                  </div>
                )}
                <div className="truncate">
                  <p className="text-sm font-medium text-white truncate">{selectedFile.name}</p>
                  <p className="text-xs text-slate-400">
                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB • {selectedFile.type || 'Archivo'}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSelectedFile(null)}
                aria-label="Quitar archivo"
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
                title="Quitar archivo"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 pointer-events-none">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 group-hover:scale-110 transition-transform">
                <Upload className="h-6 w-6" />
              </div>
              <p className="text-sm font-medium text-slate-200">
                Arrastrá tu archivo o <span className="text-indigo-400 underline">buscalo en tu PC</span>
              </p>
              <p className="text-xs text-slate-400">
                Formatos aceptados: PDFs, capturas de pantalla, diagramas (PNG, JPG, WEBP)
              </p>
            </div>
          )}
        </div>
      ) : (
        /* Anki Card Mode */
        <div>
          {selectedAnkiCard ? (
            <div className="rounded-xl border border-indigo-500/30 bg-slate-950/70 p-4 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 shrink-0">
                    <Layers className="h-5 w-5" />
                  </div>
                  <div className="truncate">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white">Tarjeta Anki #{selectedAnkiCard.note_id}</span>
                      <span className="rounded bg-indigo-950/80 border border-indigo-700/50 px-2 py-0.2 text-[10px] font-semibold text-indigo-300">
                        {selectedAnkiCard.model_name}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 truncate">Mazo: {selectedAnkiCard.deck_name}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={onOpenAnkiCardPicker}
                    className="rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:text-white transition-all"
                  >
                    Cambiar Tarjeta
                  </button>
                  <button
                    type="button"
                    onClick={onClearAnkiCard}
                    aria-label="Quitar tarjeta de Anki"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
                    title="Quitar tarjeta"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Fields preview */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                {Object.entries(selectedAnkiCard.raw_fields || {}).slice(0, 4).map(([field, val]) => (
                  <div key={field} className="rounded-lg border border-slate-800/90 bg-slate-900/60 p-2.5 text-xs">
                    <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block mb-1">
                      {field}
                    </span>
                    <p className="text-slate-200 line-clamp-2 leading-relaxed">
                      {stripHtmlAndDecode(val) || <span className="text-slate-400 italic">(vacío)</span>}
                    </p>
                  </div>
                ))}
              </div>

              {(selectedAnkiCard.tags || []).length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-800/60">
                  <span className="text-[10px] text-slate-400 font-bold uppercase">Etiquetas:</span>
                  {(selectedAnkiCard.tags || []).map((t) => (
                    <span
                      key={t}
                      className="rounded bg-slate-900 border border-slate-800 px-1.5 py-0.5 text-[9px] text-slate-400"
                    >
                      #{t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div
              onClick={isAnkiConnected ? onOpenAnkiCardPicker : undefined}
              className={`relative flex min-h-[190px] flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-all ${
                isAnkiConnected
                  ? 'border-slate-700/70 bg-slate-950/40 hover:border-indigo-500/50 hover:bg-slate-900/40 cursor-pointer group'
                  : 'border-slate-800 bg-slate-950/20 opacity-80 cursor-not-allowed'
              }`}
            >
              <div className="flex flex-col items-center gap-2.5 max-w-md">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 group-hover:scale-110 transition-transform">
                  <Layers className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">
                    {isAnkiConnected
                      ? 'Explorar y seleccionar tarjeta de Anki'
                      : 'Anki Desktop no detectado'}
                  </p>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    {isAnkiConnected
                      ? 'Navegá entre tus mazos, revisá tus notas y seleccioná la tarjeta que querés analizar o planificar.'
                      : 'Abrí Anki Desktop con el complemento AnkiConnect activado para explorar tus mazos y tarjetas.'}
                  </p>
                </div>

                {isAnkiConnected && (
                  <button
                    type="button"
                    onClick={onOpenAnkiCardPicker}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-indigo-600/30 transition-all active:scale-95"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>Abrir Explorador de Tarjetas de Anki</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
