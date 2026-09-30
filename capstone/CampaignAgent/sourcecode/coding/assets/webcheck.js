#!/usr/bin/env node
/**
 * webcheck — does this page actually work for a person?
 *
 * An agent should not have to invent a browser test harness before it can check
 * its own work. Python gets pytest pre-installed and nobody calls that cheating;
 * a web page needs the same thing. Without it the agent spends its whole run
 * debugging its test instead of its page.
 *
 *   node webcheck.js index.html
 *
 * It checks the things a DOM assertion misses:
 *   - visible text, not present text. An element left at opacity 0 by an
 *     entrance animation that never ran is invisible to a person.
 *   - the page on a file:// origin, where storage APIs throw. This is the most
 *     common way a good-looking page renders completely blank.
 *   - the page with JavaScript disabled entirely.
 *   - whether anything clickable actually changes the page.
 */
const fs = require("fs");
let JSDOM, VirtualConsole;
try { ({ JSDOM, VirtualConsole } = require("jsdom")); }
catch { console.error("webcheck needs jsdom: npm install jsdom"); process.exit(2); }

const file = process.argv[2];
if (!file) { console.error("usage: node webcheck.js <file.html>"); process.exit(2); }
const html = fs.readFileSync(file, "utf8");
const problems = [];
const note = (mode, msg) => problems.push(`[${mode}] ${msg}`);

function browserish(win, storageThrows) {
  win.matchMedia = q => ({ matches: false, media: q, addEventListener(){}, removeEventListener(){},
                           addListener(){}, removeListener(){}, onchange: null });
  win.scrollTo = () => {};
  if (storageThrows) {
    for (const name of ["localStorage", "sessionStorage"]) {
      Object.defineProperty(win, name, { configurable: true,
        get() { throw new Error("SecurityError: storage is unavailable on this origin"); } });
    }
  }
  win.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; }
    observe(el) { this.cb([{ isIntersecting: true, target: el, intersectionRatio: 1 }], this); }
    unobserve() {} disconnect() {} takeRecords() { return []; }
  };
}

function visibleText(doc, win) {
  let total = 0;
  const all = doc.body ? doc.body.querySelectorAll("*") : [];
  for (const el of all) {
    if (el.children.length) continue;
    const text = (el.textContent || "").trim();
    if (!text) continue;
    let hidden = false;
    for (let p = el; p; p = p.parentElement) {
      const s = win.getComputedStyle(p);
      if (s.display === "none" || s.visibility === "hidden" || parseFloat(s.opacity || "1") === 0) {
        hidden = true; break;
      }
    }
    if (!hidden) total += text.length;
  }
  return total;
}

function load(mode, js, storageThrows) {
  return new Promise(resolve => {
    const errs = [];
    const vc = new VirtualConsole();
    vc.on("jsdomError", e => errs.push((e.message || String(e)).split("\n")[0]));
    const dom = new JSDOM(html, {
      runScripts: js ? "dangerously" : "outside-only",
      pretendToBeVisual: true, virtualConsole: vc, url: "https://example.invalid/",
      beforeParse(win) { browserish(win, storageThrows); },
    });
    let done = false;
    const finish = () => {
      if (done) return; done = true;
      const win = dom.window, doc = win.document;
      for (const e of errs) note(mode, `JavaScript threw: ${e}`);
      const chars = visibleText(doc, win);
      if (chars < 200) note(mode, `only ${chars} characters of visible text: the page is effectively blank`);
      resolve({ dom, doc, win, chars });
    };
    if (js) { dom.window.addEventListener("load", () => setTimeout(finish, 80)); setTimeout(finish, 3000); }
    else finish();
  });
}

(async () => {
  const normal = await load("normal", true, false);
  await load("file:// origin", true, true);
  await load("no javascript", false, false);

  const { doc } = normal;
  const clickable = [...doc.querySelectorAll(
    "button,[role=button],summary,.accordion-header,[class*=toggle],[class*=tab],[class*=accordion]")].slice(0, 12);
  let responded = 0;
  for (const el of clickable) {
    const before = doc.documentElement.outerHTML.length + doc.documentElement.className + doc.body.className;
    try { el.click(); } catch (e) { note("interaction", `clicking <${el.tagName.toLowerCase()}> threw: ${e.message}`); continue; }
    const after = doc.documentElement.outerHTML.length + doc.documentElement.className + doc.body.className;
    if (after !== before) responded++;
  }
  if (clickable.length && responded === 0)
    note("interaction", `${clickable.length} clickable elements and not one changed the page`);

  console.log(`visible characters: ${normal.chars} | clickable: ${clickable.length} | responded: ${responded}`);
  if (problems.length) {
    console.error("\nFAIL");
    for (const p of problems) console.error("  " + p);
    process.exit(1);
  }
  console.log("PASS"); process.exit(0);
})();
