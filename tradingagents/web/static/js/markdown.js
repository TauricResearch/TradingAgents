// Markdown pipeline: DOMPurify.sanitize(marked.parse(md)).
//
// marked is required for GFM tables (analyst prompts mandate them).
// DOMPurify cannot block remote-image beacons — the CSP response header
// (img-src 'self' data:) is what stops that exfiltration channel.

/* global marked, DOMPurify */

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('rel', 'noopener noreferrer');
    node.setAttribute('target', '_blank');
  }
});

export function renderMarkdown(md) {
  const html = marked.parse(md ?? '', { gfm: true, breaks: false, async: false });
  return DOMPurify.sanitize(html, { FORBID_ATTR: ['style'] });
}

export function setMarkdown(element, md) {
  element.innerHTML = renderMarkdown(md);
}
