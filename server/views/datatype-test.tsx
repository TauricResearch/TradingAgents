/** @jsxImportSource hono/jsx */

export function DatatypeTestView() {
  return (
    <>
      <h3>Datatype Font Test</h3>

      <section class="panel">
        <h3>Raw expressions (2rem, calt+liga enabled)</h3>
        <div class="dt-test">
          <p>Sparkline: <code>{`{l:30,70,50,90,20,60}`}</code></p>
          <p>Bar chart: <code>{`{b:30,70,50,90,20,60}`}</code></p>
          <p>Pie chart:  <code>{`{p:75}`}</code></p>
        </div>
      </section>

      <section class="panel">
        <h3>Rendered (font-family: Datatype)</h3>
        <div class="dt-render">
          <p>Sparkline: <span>{`{l:30,70,50,90,20,60}`}</span></p>
          <p>Bar chart: <span>{`{b:30,70,50,90,20,60}`}</span></p>
          <p>Pie chart:  <span>{`{p:75}`}</span></p>
        </div>
      </section>

      <section class="panel">
        <h3>Edge cases</h3>
        <div class="dt-render">
          <p>Single bar:    <span>{`{b:50}`}</span></p>
          <p>Two values:    <span>{`{l:10,90}`}</span></p>
          <p>Pie zero:      <span>{`{p:0}`}</span></p>
          <p>Pie full:      <span>{`{p:100}`}</span></p>
          <p>Pie half:      <span>{`{p:50}`}</span></p>
          <p>Max bars (10): <span>{`{b:10,20,30,40,50,60,70,80,90,100}`}</span></p>
        </div>
      </section>

      <section class="panel">
        <h3>Variable axes</h3>
        <div class="dt-render">
          <p>Thin (wght 100):   <span style="font-variation-settings:'wdth' 100,'wght' 100">{`{l:30,70,50,90}`}</span></p>
          <p>Bold (wght 900):   <span style="font-variation-settings:'wdth' 100,'wght' 900">{`{l:30,70,50,90}`}</span></p>
          <p>Narrow (wdth 50):  <span style="font-variation-settings:'wdth' 50,'wght' 400">{`{l:30,70,50,90}`}</span></p>
          <p>Wide (wdth 150):   <span style="font-variation-settings:'wdth' 150,'wght' 400">{`{l:30,70,50,90}`}</span></p>
        </div>
      </section>

      <section class="panel">
        <h3>Font verification</h3>
        <pre id="font-info">Loading…</pre>
      </section>

      <script src="/static/scripts/datatype-test.js" />
    </>
  );
}

