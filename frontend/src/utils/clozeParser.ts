export type InlineToken =
  | {
      type: 'text';
      text: string;
      startIndex: number;
    }
  | {
      type: 'cloze';
      clozeNum: string;
      answer: string;
      hint?: string;
      isStandard: boolean;
      raw: string;
      startIndex: number;
    }
  | {
      type: 'display-math';
      math: string;
      raw: string;
      startIndex: number;
    }
  | {
      type: 'inline-math';
      math: string;
      raw: string;
      startIndex: number;
    };

export function decodeHtmlEntities(raw: string): string {
  if (!raw) return '';
  return raw.replace(
    /&(nbsp|gt|lt|quot|apos|amp|#39|#x27|#(\d+)|#x([0-9a-fA-F]+));/gi,
    (match, entity: string, dec?: string, hex?: string) => {
      if (dec !== undefined) {
        const code = parseInt(dec, 10);
        return !Number.isNaN(code) ? String.fromCodePoint(code) : match;
      }
      if (hex !== undefined) {
        const code = parseInt(hex, 16);
        return !Number.isNaN(code) ? String.fromCodePoint(code) : match;
      }
      switch (entity.toLowerCase()) {
        case 'nbsp':
          return ' ';
        case 'gt':
          return '>';
        case 'lt':
          return '<';
        case 'quot':
          return '"';
        case 'apos':
        case '#39':
        case '#x27':
          return "'";
        case 'amp':
          return '&';
        default:
          return match;
      }
    }
  );
}

export function stripHtmlAndDecode(raw: string): string {
  if (!raw) return '';
  const withoutTags = raw
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<\/p>\s*<p[^>]*>/gi, ' ')
    .replace(/<[^>]+>/g, '');
  return decodeHtmlEntities(withoutTags).replace(/\s+/g, ' ').trim();
}

type MathMode = null | '$' | '$$' | '\\(' | '\\[';

function findClosingSingleDollarOnLine(text: string, fromIdx: number): number {
  let i = fromIdx;
  while (i < text.length && text[i] !== '\n') {
    if (text[i] === '\\') {
      i += 2;
      continue;
    }
    if (text[i] === '$') {
      if (text.startsWith('$$', i)) {
        i += 2;
        continue;
      }
      return i;
    }
    i++;
  }
  return -1;
}

function splitClozeBodyAndHint(body: string): { answer: string; hint?: string } {
  let i = 0;
  let braceDepth = 0;
  let mathMode: MathMode = null;

  while (i < body.length) {
    if (body[i] === '\\') {
      if (mathMode === null && body.startsWith('\\[', i)) {
        mathMode = '\\[';
        i += 2;
        continue;
      }
      if (mathMode === null && body.startsWith('\\(', i)) {
        mathMode = '\\(';
        i += 2;
        continue;
      }
      if (mathMode === '\\[' && body.startsWith('\\]', i)) {
        mathMode = null;
        i += 2;
        continue;
      }
      if (mathMode === '\\(' && body.startsWith('\\)', i)) {
        mathMode = null;
        i += 2;
        continue;
      }
      if (
        i + 1 < body.length &&
        (body[i + 1] === '{' ||
          body[i + 1] === '}' ||
          body[i + 1] === '$' ||
          body[i + 1] === '\\')
      ) {
        i += 2;
        continue;
      }
    }

    if (mathMode === null) {
      if (body.startsWith('$$', i)) {
        mathMode = '$$';
        i += 2;
        continue;
      }
      if (body[i] === '$' && findClosingSingleDollarOnLine(body, i + 1) !== -1) {
        mathMode = '$';
        i += 1;
        continue;
      }
    } else if (mathMode === '$$' && body.startsWith('$$', i)) {
      mathMode = null;
      i += 2;
      continue;
    } else if (mathMode === '$' && body[i] === '$') {
      mathMode = null;
      i += 1;
      continue;
    }

    if (body[i] === '{') {
      braceDepth++;
      i++;
      continue;
    }

    if (body[i] === '}' && braceDepth > 0) {
      braceDepth--;
      i++;
      continue;
    }

    if (braceDepth === 0 && mathMode === null && body.startsWith('::', i)) {
      const answer = body.slice(0, i);
      const rawHint = body.slice(i + 2).trim();
      return {
        answer,
        hint: rawHint.length > 0 ? rawHint : undefined,
      };
    }

    i++;
  }

  return { answer: body };
}

function scanClozeAt(
  text: string,
  startPos: number
): { token: Extract<InlineToken, { type: 'cloze' }>; nextIndex: number; closed: boolean } | null {
  let i = startPos + 2;
  let braceDepth = 0;
  let mathMode: MathMode = null;

  while (i < text.length) {
    if (text[i] === '\\') {
      if (mathMode === null && text.startsWith('\\[', i)) {
        mathMode = '\\[';
        i += 2;
        continue;
      }
      if (mathMode === null && text.startsWith('\\(', i)) {
        mathMode = '\\(';
        i += 2;
        continue;
      }
      if (mathMode === '\\[' && text.startsWith('\\]', i)) {
        mathMode = null;
        i += 2;
        continue;
      }
      if (mathMode === '\\(' && text.startsWith('\\)', i)) {
        mathMode = null;
        i += 2;
        continue;
      }
      if (
        i + 1 < text.length &&
        (text[i + 1] === '{' ||
          text[i + 1] === '}' ||
          text[i + 1] === '$' ||
          text[i + 1] === '\\')
      ) {
        i += 2;
        continue;
      }
    }

    if (mathMode === null) {
      if (text.startsWith('$$', i)) {
        mathMode = '$$';
        i += 2;
        continue;
      }
      if (text[i] === '$' && findClosingSingleDollarOnLine(text, i + 1) !== -1) {
        mathMode = '$';
        i += 1;
        continue;
      }
    } else if (mathMode === '$$' && text.startsWith('$$', i)) {
      mathMode = null;
      i += 2;
      continue;
    } else if (mathMode === '$' && text[i] === '$') {
      mathMode = null;
      i += 1;
      continue;
    }

    if (text[i] === '{') {
      braceDepth++;
      i++;
      continue;
    }

    if (text[i] === '}') {
      if (braceDepth > 0) {
        braceDepth--;
        i++;
        continue;
      }

      if (mathMode === null && text.startsWith('}}', i)) {
        const inner = text.slice(startPos + 2, i).trim();
        const stdMatch = /^[cC](\d+)::([\s\S]*)$/.exec(inner);
        const isStandard = stdMatch !== null;
        const clozeNum = stdMatch ? stdMatch[1] : '1';
        const body = stdMatch ? stdMatch[2] : inner;
        const { answer, hint } = splitClozeBodyAndHint(body);

        if (answer.trim().length === 0) {
          return null;
        }

        return {
          token: {
            type: 'cloze',
            clozeNum,
            answer,
            hint,
            isStandard,
            raw: text.slice(startPos, i + 2),
            startIndex: startPos,
          },
          nextIndex: i + 2,
          closed: true,
        };
      }
    }

    i++;
  }

  return null;
}

export function hasUnclosedMultilineConstruct(text: string): boolean {
  let i = 0;
  while (i < text.length) {
    if (text[i] === '\\') {
      if (text.startsWith('\\[', i)) {
        const closeIdx = text.indexOf('\\]', i + 2);
        if (closeIdx === -1) return true;
        i = closeIdx + 2;
        continue;
      }
      if (text.startsWith('\\(', i)) {
        const closeIdx = text.indexOf('\\)', i + 2);
        if (closeIdx === -1) return false;
        i = closeIdx + 2;
        continue;
      }
      i += 2;
      continue;
    }

    if (text.startsWith('{{', i)) {
      const scanned = scanClozeAt(text, i);
      if (!scanned) {
        // Check if empty {{}} vs genuinely unclosed {{
        const simpleClose = text.indexOf('}}', i + 2);
        if (simpleClose === -1) return true;
        i = simpleClose + 2;
        continue;
      }
      i = scanned.nextIndex;
      continue;
    }

    if (text.startsWith('$$', i)) {
      const closeIdx = text.indexOf('$$', i + 2);
      if (closeIdx === -1) return true;
      i = closeIdx + 2;
      continue;
    }

    i++;
  }
  return false;
}

export function tokenizeInlineContent(text: string): InlineToken[] {
  if (!text) return [];

  const tokens: InlineToken[] = [];
  let pos = 0;
  let textStart = 0;

  const flushText = (endPos: number) => {
    if (endPos > textStart) {
      tokens.push({
        type: 'text',
        text: text.slice(textStart, endPos),
        startIndex: textStart,
      });
    }
  };

  while (pos < text.length) {
    // 1. Escaped characters outside tokens
    if (text[pos] === '\\') {
      if (text.startsWith('\\[', pos)) {
        const closeIdx = text.indexOf('\\]', pos + 2);
        if (closeIdx !== -1 && closeIdx > pos + 2) {
          flushText(pos);
          tokens.push({
            type: 'display-math',
            math: text.slice(pos + 2, closeIdx),
            raw: text.slice(pos, closeIdx + 2),
            startIndex: pos,
          });
          pos = closeIdx + 2;
          textStart = pos;
          continue;
        }
      } else if (text.startsWith('\\(', pos)) {
        const closeIdx = text.indexOf('\\)', pos + 2);
        if (closeIdx !== -1 && closeIdx > pos + 2) {
          flushText(pos);
          tokens.push({
            type: 'inline-math',
            math: text.slice(pos + 2, closeIdx),
            raw: text.slice(pos, closeIdx + 2),
            startIndex: pos,
          });
          pos = closeIdx + 2;
          textStart = pos;
          continue;
        }
      } else if (pos + 1 < text.length && text[pos + 1] === '$') {
        pos += 2;
        continue;
      }
    }

    // 2. Cloze deletion: {{c1::...}} or bare {{...}}
    if (text.startsWith('{{', pos)) {
      const clozeResult = scanClozeAt(text, pos);
      if (clozeResult) {
        flushText(pos);
        tokens.push(clozeResult.token);
        pos = clozeResult.nextIndex;
        textStart = pos;
        continue;
      }
    }

    // 3. Display math: $$...$$
    if (text.startsWith('$$', pos)) {
      const closeIdx = text.indexOf('$$', pos + 2);
      if (closeIdx !== -1 && closeIdx > pos + 2) {
        flushText(pos);
        tokens.push({
          type: 'display-math',
          math: text.slice(pos + 2, closeIdx),
          raw: text.slice(pos, closeIdx + 2),
          startIndex: pos,
        });
        pos = closeIdx + 2;
        textStart = pos;
        continue;
      }
    }

    // 4. Inline math: $...$
    if (text[pos] === '$' && !text.startsWith('$$', pos)) {
      const closeIdx = findClosingSingleDollarOnLine(text, pos + 1);
      if (closeIdx !== -1 && closeIdx > pos + 1) {
        flushText(pos);
        tokens.push({
          type: 'inline-math',
          math: text.slice(pos + 1, closeIdx),
          raw: text.slice(pos, closeIdx + 1),
          startIndex: pos,
        });
        pos = closeIdx + 1;
        textStart = pos;
        continue;
      }
    }

    pos++;
  }

  flushText(text.length);
  return tokens;
}

export function extractFirstClozeAnswer(text: string): string | null {
  if (!text) return null;
  const tokens = tokenizeInlineContent(text);
  const standardCloze = tokens.find(
    (t): t is Extract<InlineToken, { type: 'cloze' }> =>
      t.type === 'cloze' && t.isStandard && t.answer.trim().length > 0
  );
  if (standardCloze) {
    return standardCloze.answer.trim();
  }
  const anyCloze = tokens.find(
    (t): t is Extract<InlineToken, { type: 'cloze' }> =>
      t.type === 'cloze' && t.answer.trim().length > 0
  );
  return anyCloze ? anyCloze.answer.trim() : null;
}
