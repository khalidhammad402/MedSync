/* MedSync UI helpers: call timer, panels, toasts, sliders and the scripted demo. No dependencies but htmx. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var store = {
    get: function (k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (e) { return null; } },
    set: function (k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  };

  /* ---------- toasts ---------- */
  function toast(text, bad) {
    var el = document.createElement("div");
    el.className = "toast" + (bad ? " bad" : "");
    el.textContent = text;
    $("#toasts").appendChild(el);
  }
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) { if (n.nodeType === 1) setTimeout(function () { n.remove(); }, 4500); });
    });
  }).observe($("#toasts"), { childList: true });

  /* Friendly errors: the server always answers with {error, message}. */
  document.body.addEventListener("htmx:responseError", function (e) {
    var message = "Something went wrong. Please try again.";
    try { message = JSON.parse(e.detail.xhr.responseText).message || message; } catch (err) { /* keep default */ }
    toast(message, true);
  });
  document.body.addEventListener("htmx:sendError", function (e) {
    if (e.detail.elt && e.detail.elt.id === "poller") return;
    toast("MedSync is not reachable. Is the app still running?", true);
  });

  /* ---------- panels and modals ---------- */
  function close(id) { var el = document.getElementById(id); if (el) el.innerHTML = ""; }
  document.addEventListener("click", function (e) {
    var closer = e.target.closest("[data-close]");
    if (closer) { close(closer.getAttribute("data-close")); return; }
    if (e.target.classList.contains("modal")) { close("modal"); return; }
    var then = e.target.closest("[data-then]");
    if (then) htmx.ajax("GET", then.getAttribute("data-then"), { target: then.getAttribute("data-then-target"), swap: "innerHTML" });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { close("modal"); close("side-panel"); }
    if (e.key === "Enter" && !e.shiftKey && e.target.id === "utterance-input") {
      e.preventDefault();
      e.target.form.requestSubmit();
    }
  });
  document.body.addEventListener("close-modal", function () { setTimeout(function () { close("modal"); }, 900); });

  /* ---------- call timer and "in call" state ---------- */
  function tick() {
    var co = $("#copilot [data-started]");
    document.body.classList.toggle("in-call", !!co);
    var out = $("#call-timer");
    if (!out) return;
    if (!co) { out.textContent = "00:00"; return; }
    var secs = Math.max(0, Math.floor((Date.now() - new Date(co.getAttribute("data-started")).getTime()) / 1000));
    out.textContent = String(Math.floor(secs / 60)).padStart(2, "0") + ":" + String(secs % 60).padStart(2, "0");
  }
  setInterval(tick, 1000);
  tick();
  document.body.addEventListener("htmx:afterSwap", function (e) {
    tick();
    if (e.detail.target && e.detail.target.id === "copilot") { var i = $("#utterance-input"); if (i) i.focus(); }
  });

  /* Remember the running call so the Consult tab comes back to it. */
  if (location.pathname === "/consult") store.set("consultUrl", location.pathname + location.search.replace(/[?&]demo=\w+/, ""));
  document.body.addEventListener("htmx:replacedInHistory", function () { store.set("consultUrl", location.pathname + location.search); });
  var consultTab = $("#tab-consult");
  if (consultTab && store.get("consultUrl")) consultTab.setAttribute("href", store.get("consultUrl"));

  /* ---------- scripted demo ---------- */
  var demo = { steps: [], timer: null, runId: 0 };
  var PAGES = { consult: "/consult", simulator: "/simulator", explorer: "/explorer" };

  function demoState() { return store.get("demo"); }
  function setDemo(s) { store.set("demo", s); }

  async function waitFor(sel, ms) {
    var end = Date.now() + (ms || 5000);
    while (Date.now() < end) { var el = $(sel); if (el) return el; await sleep(60); }
    return null;
  }
  function spotlight(sel) {
    document.querySelectorAll(".spot").forEach(function (el) { el.classList.remove("spot"); });
    document.querySelectorAll(sel).forEach(function (el) { el.classList.add("spot"); });
    var first = $(sel);
    if (first) first.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  async function typeInto(input, text, alive) {
    input.focus();
    input.value = "";
    for (var i = 0; i < text.length && alive(); i++) { input.value += text[i]; await sleep(28); }
    input.value = text;
  }
  async function act(a, alive) {
    if (a.do === "wait") { await sleep(a.ms); return; }
    if (a.do === "spotlight") { await waitFor(a.sel, 3000); spotlight(a.sel); return; }
    if (a.do === "start_call") {
      if (!$("#utterance-input")) { $("#start-call").click(); await waitFor("#utterance-input"); }
      return;
    }
    if (a.do === "utter") {
      var input = await waitFor("#utterance-input");
      if (!input) return;
      await typeInto(input, a.text, alive);
      await sleep(350);
      var before = $("#copilot .copilot");
      input.form.requestSubmit();
      for (var n = 0; n < 60 && $("#copilot .copilot") === before; n++) await sleep(50);
      await sleep(500);
      return;
    }
    if (a.do === "confirm") {
      var c = await waitFor("#confirm-identity", 3000);
      if (c) { spotlight("#next-question"); await sleep(1200); c.click(); await waitFor("#identity-confirmed", 3000); }
      return;
    }
    if (a.do === "simulate") {
      var btn = await waitFor("#sim-" + a.action);
      if (btn) { spotlight("#sim-" + a.action); await sleep(700); btn.click(); await sleep(1300); spotlight("#mini-1"); }
      return;
    }
    if (a.do === "open_key") { var k = await waitFor("#open-key"); if (k) k.click(); await waitFor("#whats-new", 3000); spotlight("#whats-new"); }
  }

  function renderBar(s) {
    var step = demo.steps[s.i], bar = $("#demo-bar");
    bar.hidden = false;
    document.body.classList.add("demo-on");
    $("#demo-count").textContent = "Step " + step.n + " of " + demo.steps[demo.steps.length - 1].n;
    $("#demo-title").textContent = step.title;
    $("#demo-say").textContent = step.say;
    $("#demo-pause").textContent = s.playing ? "Pause" : "Play";
  }
  function targetUrl(step) {
    if (step.page === "consult") {
      if (step.fresh) return "/consult?patient_id=1";
      var saved = store.get("consultUrl");
      return saved && saved.indexOf("patient_id=1") >= 0 ? saved : "/consult?patient_id=1";
    }
    return PAGES[step.page];
  }
  async function runStep() {
    var s = demoState();
    if (!s || !s.on) return;
    var step = demo.steps[s.i];
    if (!step) { stopDemo(); return; }   /* a tab that remembers an older, longer demo */
    if (location.pathname !== PAGES[step.page]) { location.href = targetUrl(step); return; }
    renderBar(s);
    close("modal"); close("side-panel");
    var id = ++demo.runId, started = Date.now();
    var alive = function () { return id === demo.runId; };
    var bar = $("#demo-progress");
    bar.style.transition = "none"; bar.style.width = "0%";
    for (var i = 0; i < step.actions.length && alive(); i++) await act(step.actions[i], alive);
    if (!alive()) return;
    var left = Math.max(800, step.seconds * 1000 - (Date.now() - started));
    void bar.offsetWidth;
    bar.style.transition = "width " + left + "ms linear"; bar.style.width = "100%";
    clearTimeout(demo.timer);
    if (demoState().playing) demo.timer = setTimeout(function () { if (alive()) go(1); }, left);
  }
  function go(delta) {
    var s = demoState();
    if (!s) return;
    clearTimeout(demo.timer);
    demo.runId++;
    var next = s.i + delta;
    if (next < 0) next = 0;
    if (next >= demo.steps.length) {
      s.playing = false; setDemo(s);
      $("#demo-count").textContent = "Demo finished";
      $("#demo-pause").textContent = "Restart";
      $("#demo-pause").setAttribute("data-restart", "1");
      return;
    }
    s.i = next; setDemo(s);
    runStep();
  }
  function stopDemo() {
    clearTimeout(demo.timer); demo.runId++;
    setDemo(null);
    $("#demo-bar").hidden = true;
    document.body.classList.remove("demo-on");
    document.querySelectorAll(".spot").forEach(function (el) { el.classList.remove("spot"); });
  }
  async function startDemo() {
    await fetch("/simulator/reset", { method: "POST", headers: { accept: "application/json" } });
    store.set("consultUrl", null);
    setDemo({ on: true, i: 0, playing: true });
    location.href = "/consult?patient_id=1";
  }
  $("#run-demo").addEventListener("click", startDemo);
  $("#demo-next").addEventListener("click", function () { go(1); });
  $("#demo-back").addEventListener("click", function () { go(-1); });
  $("#demo-stop").addEventListener("click", stopDemo);
  $("#demo-pause").addEventListener("click", function (e) {
    if (e.target.getAttribute("data-restart")) { startDemo(); return; }
    var s = demoState();
    s.playing = !s.playing; setDemo(s);
    e.target.textContent = s.playing ? "Pause" : "Play";
    if (s.playing) go(0 + 1); else { clearTimeout(demo.timer); $("#demo-progress").style.transition = "none"; }
  });

  if (/[?&]open=key/.test(location.search) && $("#open-key")) $("#open-key").click();

  if (/[?&]demo=start/.test(location.search)) { startDemo(); return; }
  if (demoState() && demoState().on) {
    fetch("/demo/scenario").then(function (r) { return r.json(); }).then(function (d) { demo.steps = d.steps; runStep(); });
  }
})();
