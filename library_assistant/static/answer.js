// A model writes Markdown, and a Student shouldn't have to read it. This turns an answer
// into paragraphs, headings, lists, and tables. It builds elements and sets their text,
// never HTML, so nothing a model writes can run as markup.

const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const HEADING = /^#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const LINE_RULE = /^\s*([-*_])\1{2,}\s*$/;

const cells = (line) =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());

const startsTable = (lines, at) =>
  lines[at].includes("|") &&
  at + 1 < lines.length &&
  lines[at + 1].includes("-") &&
  lines[at + 1].includes("|") &&
  TABLE_RULE.test(lines[at + 1]);

const listItem = (line) => {
  const bullet = line.match(BULLET);
  if (bullet) return { ordered: false, text: bullet[1] };
  const numbered = line.match(NUMBERED);
  if (numbered) return { ordered: true, start: Number(numbered[1]), text: numbered[2] };
  return null;
};

// A blank line between items doesn't end a list: models often write them that way.
const nextLine = (lines, at) => {
  while (at < lines.length && !lines[at].trim()) at += 1;
  return at;
};

function answerBlocks(text) {
  const lines = text.split("\n");
  const blocks = [];
  let at = 0;
  while (at < lines.length) {
    const line = lines[at];
    const item = listItem(line);
    if (!line.trim() || LINE_RULE.test(line)) {
      at += 1;
    } else if (startsTable(lines, at)) {
      const rows = [];
      for (at += 2; at < lines.length && lines[at].includes("|"); at += 1) {
        rows.push(cells(lines[at]));
      }
      blocks.push({ type: "table", header: cells(line), rows });
    } else if (HEADING.test(line)) {
      blocks.push({ type: "heading", text: line.match(HEADING)[1] });
      at += 1;
    } else if (item) {
      const list = { type: "list", ordered: item.ordered, start: item.start, items: [] };
      let next = item;
      while (next && next.ordered === list.ordered) {
        list.items.push(next.text);
        at = nextLine(lines, at + 1);
        next = at < lines.length ? listItem(lines[at]) : null;
      }
      blocks.push(list);
    } else {
      const paragraph = [];
      while (
        at < lines.length &&
        lines[at].trim() &&
        !HEADING.test(lines[at]) &&
        !listItem(lines[at]) &&
        !LINE_RULE.test(lines[at]) &&
        !startsTable(lines, at)
      ) {
        paragraph.push(lines[at]);
        at += 1;
      }
      blocks.push({ type: "paragraph", text: paragraph.join("\n") });
    }
  }
  return blocks;
}

// **bold**, *italic*, and `code`, which can nest. An unclosed marker stays as it is.
const INLINE = /\*\*(.+?)\*\*(?!\*)|\*(\S(?:.*?\S)?)\*|`(.+?)`/s;

function inlineParts(text) {
  const parts = [];
  let rest = text;
  for (let match = rest.match(INLINE); match; match = rest.match(INLINE)) {
    if (match.index) parts.push({ text: rest.slice(0, match.index) });
    if (match[1] !== undefined) parts.push({ tag: "strong", parts: inlineParts(match[1]) });
    else if (match[2] !== undefined) parts.push({ tag: "em", parts: inlineParts(match[2]) });
    else parts.push({ tag: "code", parts: [{ text: match[3] }] });
    rest = rest.slice(match.index + match[0].length);
  }
  if (rest) parts.push({ text: rest });
  return parts;
}

function addInline(element, text) {
  const add = (parent, parts) => {
    for (const part of parts) {
      if (part.tag) {
        const child = document.createElement(part.tag);
        add(child, part.parts);
        parent.append(child);
      } else {
        parent.append(document.createTextNode(part.text));
      }
    }
  };
  add(element, inlineParts(text));
  return element;
}

function tableElement(block) {
  const scroll = document.createElement("div");
  scroll.className = "answer-table";
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const cell of block.header) headRow.append(addInline(document.createElement("th"), cell));
  head.append(headRow);
  const body = document.createElement("tbody");
  for (const row of block.rows) {
    const tr = document.createElement("tr");
    for (const cell of row) tr.append(addInline(document.createElement("td"), cell));
    body.append(tr);
  }
  table.append(head, body);
  scroll.append(table);
  return scroll;
}

function renderAnswer(element, text) {
  element.replaceChildren();
  for (const block of answerBlocks(text)) {
    if (block.type === "table") {
      element.append(tableElement(block));
    } else if (block.type === "list") {
      const list = document.createElement(block.ordered ? "ol" : "ul");
      if (block.ordered && block.start !== 1) list.start = block.start;
      for (const item of block.items) list.append(addInline(document.createElement("li"), item));
      element.append(list);
    } else {
      const tag = block.type === "heading" ? "h3" : "p";
      element.append(addInline(document.createElement(tag), block.text));
    }
  }
}

if (typeof module !== "undefined") module.exports = { answerBlocks, inlineParts };
