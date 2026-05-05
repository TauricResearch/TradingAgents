/**
 * Datatype Test view client-side script.
 */
export function testScript(): string {
  return `
// Check if the font loaded and has the right features
document.fonts.ready.then(function() {
  var info = document.getElementById('font-info');
  var font = document.fonts.check('16px Datatype');
  var entries = [];
  entries.push('Font ready: ' + font);

  // Check font-feature-settings on first .dt-render span
  var el = document.querySelector('.dt-render span');
  if (el) {
    var cs = getComputedStyle(el);
    entries.push('font-family: ' + cs.fontFamily);
    entries.push('font-feature-settings: ' + cs.fontFeatureSettings);
    entries.push('font-variation-settings: ' + cs.fontVariationSettings);
  }

  info.textContent = entries.join('\\n');
});`
}
