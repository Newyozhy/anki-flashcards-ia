import React, { useState } from 'react';
import katex from 'katex';
import { getMediaUrl } from '../services/api';
import {
  decodeHtmlEntities,
  hasUnclosedMultilineConstruct,
  tokenizeInlineContent,
} from '../utils/clozeParser';

interface CardContentRendererProps {
  content: string;
  mode?: 'front' | 'back' | 'extra';
  className?: string;
}

const katexCache = new Map<string, string>();
const MAX_KATEX_CACHE_SIZE = 500;

function renderMath(mathStr: string, displayMode: boolean): React.ReactNode {
  try {
    const trimmed = mathStr.trim();
    const cacheKey = `${displayMode ? 'D' : 'I'}:${trimmed}`;
    let html = katexCache.get(cacheKey);
    if (html === undefined) {
      html = katex.renderToString(trimmed, {
        displayMode,
        throwOnError: false,
      });
      if (katexCache.size >= MAX_KATEX_CACHE_SIZE) {
        const firstKey = katexCache.keys().next().value;
        if (firstKey !== undefined) {
          katexCache.delete(firstKey);
        }
      }
      katexCache.set(cacheKey, html);
    }
    return (
      <span
        className={displayMode ? 'block my-2 text-center overflow-x-auto' : 'inline-block px-0.5'}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <code>{mathStr}</code>;
  }
}

const WRAPPER_TAG_REGEX =
  /<\/?(?:div|span|p|br|hr|ul|ol|li|pre|blockquote|h[1-6]|table|thead|tbody|tr|td|th|font|u|s|sub|sup|small|mark|center|section|article|header|footer|nav|a)\b[^>]*>/gi;

const STRAY_HTML_TAG_REGEX =
  /<\/?(?:b|strong|i|em|code|div|span|p|br|hr|ul|ol|li|pre|blockquote|h[1-6]|table|thead|tbody|tr|td|th|font|u|s|sub|sup|small|mark|center|section|article|header|footer|nav|a|img)\b[^>]*>/gi;

function stripRemainingHtmlTags(raw: string): string {
  if (!raw) return '';
  return decodeHtmlEntities(raw.replace(STRAY_HTML_TAG_REGEX, ''));
}

function sanitizeText(raw: string): string {
  if (!raw) return '';
  const normalized = raw
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>\s*<p[^>]*>/gi, '\n\n')
    .replace(/<li[^>]*>/gi, '\n• ')
    .replace(/<(b|strong|i|em|code)\b[^>]*>/gi, '<$1>')
    .replace(/<\/(b|strong|i|em|code)\s*>/gi, '</$1>')
    .replace(WRAPPER_TAG_REGEX, '');
  return decodeHtmlEntities(normalized).trim();
}

function renderFormattedText(text: string, keyPrefix: string): React.ReactNode[] {
  if (!text) return [];

  const formatRegex =
    /(`([^`\n]+)`|<code\b[^>]*>([\s\S]+?)<\/code>|\*\*([\s\S]+?)\*\*|<(?:b|strong)\b[^>]*>([\s\S]+?)<\/(?:b|strong)>|(?<!\*)\*([^*\n]+?)\*(?!\*)|<(?:i|em)\b[^>]*>([\s\S]+?)<\/(?:i|em)>)/gi;

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = formatRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const plainSegment = stripRemainingHtmlTags(text.slice(lastIndex, match.index));
      if (plainSegment) {
        nodes.push(
          <span key={`${keyPrefix}-txt-${lastIndex}`}>{plainSegment}</span>
        );
      }
    }

    const inlineCode = match[2] ?? match[3];
    const boldText = match[4] ?? match[5];
    const italicText = match[6] ?? match[7];

    if (inlineCode !== undefined) {
      nodes.push(
        <code
          key={`${keyPrefix}-code-${match.index}`}
          className="px-1.5 py-0.5 rounded bg-slate-800/90 text-indigo-300 font-mono text-[0.9em] border border-slate-700/60"
        >
          {stripRemainingHtmlTags(inlineCode)}
        </code>
      );
    } else if (boldText !== undefined) {
      nodes.push(
        <strong
          key={`${keyPrefix}-bold-${match.index}`}
          className="font-bold text-white"
        >
          {renderFormattedText(boldText, `${keyPrefix}-b-${match.index}`)}
        </strong>
      );
    } else if (italicText !== undefined) {
      nodes.push(
        <em
          key={`${keyPrefix}-italic-${match.index}`}
          className="italic text-indigo-100"
        >
          {renderFormattedText(italicText, `${keyPrefix}-i-${match.index}`)}
        </em>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    const remaining = stripRemainingHtmlTags(text.slice(lastIndex));
    if (remaining) {
      nodes.push(
        <span key={`${keyPrefix}-txt-${lastIndex}`}>{remaining}</span>
      );
    }
  }

  return nodes;
}

function renderInlineText(text: string, mode: 'front' | 'back' | 'extra'): React.ReactNode[] {
  if (!text) return [];

  const tokens = tokenizeInlineContent(text);
  const elements: React.ReactNode[] = [];

  for (const token of tokens) {
    if (token.type === 'text') {
      elements.push(...renderFormattedText(token.text, `seg-${token.startIndex}`));
      continue;
    }

    if (token.type === 'cloze') {
      const { clozeNum, answer, hint, startIndex } = token;
      const isBack = mode === 'back';

      const badgeBg = isBack
        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
        : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40';
      const numBg = isBack
        ? 'bg-emerald-950/80 text-emerald-400 border-emerald-700/50'
        : 'bg-indigo-950/80 text-indigo-400 border-indigo-700/50';

      elements.push(
        <span
          key={`cloze-${startIndex}`}
          className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold border ${badgeBg} shadow-sm my-0.5 align-baseline`}
          title={
            isBack
              ? 'Respuesta revelada'
              : `Oclusión activa: "${stripRemainingHtmlTags(answer)}" (Anki Cloze)`
          }
        >
          <span className={`text-[9px] font-mono font-bold px-1 rounded border ${numBg}`}>
            c{clozeNum}
          </span>
          <span>
            {isBack ? (
              renderInlineText(answer, mode)
            ) : (
              <span className="font-mono text-indigo-300 font-bold px-0.5">
                [...]
              </span>
            )}
          </span>
          {hint && (
            <span className="text-[10px] text-slate-400 italic opacity-90">
              ({stripRemainingHtmlTags(hint)})
            </span>
          )}
        </span>
      );
      continue;
    }

    if (token.type === 'display-math') {
      elements.push(
        <React.Fragment key={`dmath-${token.startIndex}`}>
          {renderMath(token.math, true)}
        </React.Fragment>
      );
      continue;
    }

    if (token.type === 'inline-math') {
      elements.push(
        <React.Fragment key={`imath-${token.startIndex}`}>
          {renderMath(token.math, false)}
        </React.Fragment>
      );
    }
  }

  return elements;
}

const CardMediaImage: React.FC<{ src: string; alt?: string }> = ({ src, alt }) => {
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    return (
      <div className="my-3 flex flex-col items-center justify-center rounded-xl border border-amber-500/40 bg-amber-950/20 p-4 text-center shadow-sm max-w-full">
        <span className="text-xs font-semibold text-amber-300">
          ⚠️ Recurso multimedia no encontrado en Anki ({src})
        </span>
        {alt && alt !== 'Diagrama pedagógico' && (
          <span className="text-[10px] text-amber-200/70 mt-1 italic">
            {alt}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="my-3 flex flex-col items-center justify-center rounded-xl overflow-hidden border border-slate-700/60 bg-slate-950/80 p-3 shadow-md max-w-full">
      <img
        src={getMediaUrl(src)}
        alt={alt || 'Diagrama asociado'}
        onError={() => setHasError(true)}
        className="max-h-64 max-w-full rounded-lg object-contain shadow-sm border border-slate-800"
        loading="lazy"
      />
      <span className="text-[10px] text-slate-400 mt-1.5 font-medium flex items-center gap-1">
        🖼️ {alt || 'Diagrama pedagógico asociado'}
      </span>
    </div>
  );
};

export const CardContentRenderer: React.FC<CardContentRendererProps> = React.memo(({
  content,
  mode = 'front',
  className = '',
}) => {
  if (!content) return null;

  // Normalize HTML block/line tags before splitting into lines
  const normalizedContent = content
    .replace(/\r\n/g, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>\s*<p[^>]*>/gi, '\n\n')
    .replace(/<li[^>]*>/gi, '\n• ')
    .replace(/<\/li>/gi, '');

  const rawSections = normalizedContent.split('\n');
  type RenderBlock =
    | { type: 'table'; lines: string[] }
    | { type: 'image'; src: string; alt?: string }
    | { type: 'ascii'; text: string }
    | { type: 'warning'; text: string }
    | { type: 'text'; text: string };

  const blocks: RenderBlock[] = [];
  let currentTableLines: string[] | null = null;
  let currentAsciiLines: string[] | null = null;

  for (let i = 0; i < rawSections.length; i++) {
    let rawLine = rawSections[i];
    let trimmed = rawLine.trim();

    // Check if line contains one or more images (<img src="..."> or ![alt](src))
    const imagePattern =
      /<img\b[^>]*?\bsrc=["']([^"']+)["'][^>]*>|!\[([^\]]*)\]\(([^)]+)\)/gi;
    if (!currentAsciiLines && imagePattern.test(trimmed)) {
      if (currentTableLines) {
        blocks.push({ type: 'table', lines: currentTableLines });
        currentTableLines = null;
      }

      imagePattern.lastIndex = 0;
      let lastImgIdx = 0;
      let imgMatch: RegExpExecArray | null;

      while ((imgMatch = imagePattern.exec(trimmed)) !== null) {
        if (imgMatch.index > lastImgIdx) {
          const textBefore = sanitizeText(trimmed.slice(lastImgIdx, imgMatch.index));
          if (textBefore) {
            blocks.push({ type: 'text', text: textBefore });
          }
        }

        const isHtmlImg = imgMatch[1] !== undefined;
        const src = (isHtmlImg ? imgMatch[1] : imgMatch[3])?.trim();
        let alt = 'Diagrama pedagógico';
        if (isHtmlImg) {
          const altAttr = /\balt=["']([^"']*)["']/i.exec(imgMatch[0]);
          if (altAttr && altAttr[1].trim()) {
            alt = altAttr[1].trim();
          }
        } else if (imgMatch[2] && imgMatch[2].trim()) {
          alt = imgMatch[2].trim();
        }

        if (src) {
          blocks.push({ type: 'image', src, alt });
        }

        lastImgIdx = imgMatch.index + imgMatch[0].length;
      }

      if (lastImgIdx < trimmed.length) {
        const textAfter = sanitizeText(trimmed.slice(lastImgIdx));
        if (textAfter) {
          blocks.push({ type: 'text', text: textAfter });
        }
      }
      continue;
    }

    // Check if line is part of a Markdown table
    const isTableRow = trimmed.startsWith('|') && trimmed.endsWith('|');
    if (isTableRow && !currentAsciiLines) {
      if (!currentTableLines) {
        currentTableLines = [];
      }
      currentTableLines.push(trimmed);
      continue;
    } else if (currentTableLines) {
      blocks.push({ type: 'table', lines: currentTableLines });
      currentTableLines = null;
    }

    // Check for ASCII block header or content
    if (
      trimmed.startsWith('ASCII:') ||
      trimmed.startsWith('```ASCII') ||
      trimmed.startsWith('```text')
    ) {
      if (currentAsciiLines) {
        blocks.push({ type: 'ascii', text: currentAsciiLines.join('\n') });
      }
      currentAsciiLines = [trimmed];
      continue;
    }

    if (currentAsciiLines) {
      if (
        trimmed === '```' ||
        trimmed.startsWith('⚠️') ||
        trimmed.startsWith('Tabla') ||
        trimmed.startsWith('<div') ||
        trimmed === ''
      ) {
        if (trimmed !== '```' && trimmed !== '') {
          blocks.push({ type: 'ascii', text: currentAsciiLines.join('\n') });
          currentAsciiLines = null;
        } else if (trimmed === '```') {
          blocks.push({ type: 'ascii', text: currentAsciiLines.join('\n') });
          currentAsciiLines = null;
          continue;
        } else {
          currentAsciiLines.push(rawLine);
          continue;
        }
      } else {
        currentAsciiLines.push(rawLine);
        continue;
      }
    }

    // Accumulate multi-line display math ($$ ... $$, \[ ... \]) or multi-line Cloze ({{ ... }})
    while (i + 1 < rawSections.length && hasUnclosedMultilineConstruct(rawLine)) {
      i++;
      rawLine += '\n' + rawSections[i];
    }
    trimmed = rawLine.trim();

    // Check for Trampa Frecuente / Warning
    if (
      trimmed.startsWith('⚠️') ||
      trimmed.toLowerCase().includes('trampa frecuente')
    ) {
      blocks.push({ type: 'warning', text: sanitizeText(trimmed) });
      continue;
    }

    // Regular text line
    const cleaned = sanitizeText(trimmed);
    if (cleaned) {
      blocks.push({ type: 'text', text: cleaned });
    }
  }

  if (currentTableLines) {
    blocks.push({ type: 'table', lines: currentTableLines });
  }
  if (currentAsciiLines) {
    blocks.push({ type: 'ascii', text: currentAsciiLines.join('\n') });
  }

  return (
    <div className={`space-y-2.5 leading-relaxed max-w-[65ch] ${className}`}>
      {blocks.map((block, bi) => {
        if (block.type === 'image') {
          return (
            <CardMediaImage
              key={`${bi}-${block.src}`}
              src={block.src}
              alt={block.alt}
            />
          );
        }

        if (block.type === 'warning') {
          return (
            <div
              key={bi}
              className="my-2 rounded-xl bg-amber-950/30 border border-amber-500/30 p-3 text-xs text-amber-200 flex items-start gap-2.5 shadow-sm"
            >
              <span className="text-amber-400 text-base leading-none shrink-0">
                ⚠️
              </span>
              <div className="leading-relaxed font-medium">
                {renderInlineText(block.text.replace(/^⚠️\s*/, ''), mode)}
              </div>
            </div>
          );
        }

        if (block.type === 'ascii') {
          const cleanAscii = block.text
            .replace(/^```(ASCII|text)?/i, '')
            .replace(/```$/, '')
            .replace(/&gt;/g, '>')
            .replace(/&lt;/g, '<')
            .trim();
          return (
            <div
              key={bi}
              className="my-2 rounded-xl bg-slate-950/90 border border-indigo-900/50 p-3 font-mono text-xs text-indigo-300 overflow-x-auto whitespace-pre leading-snug shadow-inner"
            >
              {cleanAscii}
            </div>
          );
        }

        if (block.type === 'table') {
          const rawRows = block.lines
            .map((l) =>
              l
                .split('|')
                .map((c) => c.trim())
                .filter((_, i, arr) => i > 0 && i < arr.length - 1)
            )
            .filter((r) => r.length > 0);

          if (rawRows.length === 0) return null;

          let headerRow: string[] = [];
          let dataRows = rawRows;

          if (
            rawRows.length > 1 &&
            rawRows[1].every((cell) => /^[:\-\s]+$/.test(cell))
          ) {
            headerRow = rawRows[0];
            dataRows = rawRows.slice(2);
          } else if (rawRows.length > 1) {
            headerRow = rawRows[0];
            dataRows = rawRows.slice(1);
          }

          return (
            <div
              key={bi}
              className="my-2.5 overflow-x-auto rounded-xl border border-slate-700/80 bg-slate-950/70 shadow-inner max-w-full"
            >
              <table className="w-full text-left text-xs border-collapse">
                {headerRow.length > 0 && (
                  <thead>
                    <tr className="border-b border-slate-700 bg-indigo-950/50 text-indigo-200 font-semibold">
                      {headerRow.map((cell, ci) => (
                        <th
                          key={ci}
                          className="px-3 py-2 border-r border-slate-700/50 last:border-r-0 whitespace-nowrap"
                        >
                          {renderInlineText(sanitizeText(cell), mode)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody className="divide-y divide-slate-800/80">
                  {dataRows.map((row, ri) => (
                    <tr
                      key={ri}
                      className="hover:bg-indigo-900/10 transition-colors even:bg-slate-900/30"
                    >
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className="px-3 py-2 text-slate-200 border-r border-slate-800/50 last:border-r-0"
                        >
                          {renderInlineText(sanitizeText(cell), mode)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        return (
          <div key={bi} className="whitespace-pre-wrap">
            {renderInlineText(block.text, mode)}
          </div>
        );
      })}
    </div>
  );
});