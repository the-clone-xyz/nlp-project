#!/usr/bin/env python3
"""Browser dashboard untuk analisis dan scraping ulasan Tokopedia."""

import asyncio
import ast
import csv
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = "0.0.0.0"
DISPLAY_HOST = "127.0.0.1"
PORT = 8000
CSV_FILE = Path("dataset_ulasan_tokopedia.csv")
JSON_FILE = Path("dataset_ulasan_tokopedia.json")
SCRAPE_TIMEOUT_SECONDS = 240


def can_launch_headed_browser() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True

scrape_state = {
    "running": False,
    "success": None,
    "message": "Siap.",
    "count": 0,
    "logs": ["Siap. Masukkan URL produk lalu mulai ambil data."],
}
scrape_state_lock = threading.Lock()


def parse_literal(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, type(fallback)):
            return parsed
    except Exception:
        return fallback
    return fallback


def append_scrape_log(message):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    with scrape_state_lock:
        logs = list(scrape_state.get("logs", []))
        logs.append(line)
        scrape_state["logs"] = logs[-250:]


class ScrapeLogHandler(logging.Handler):
    def emit(self, record):
        try:
            append_scrape_log(self.format(record))
        except Exception:
            return


HTML = r"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tokopedia Review Dashboard</title>
  <style>
    :root {
      --bg: #f3f4f6;
      --panel: #ffffff;
      --line: #d8dee8;
      --muted: #64748b;
      --text: #111827;
      --blue: #2563eb;
      --green: #10b981;
      --red: #ef4444;
      --amber: #f59e0b;
      --cyan: #0ea5e9;
      --violet: #7c3aed;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, Segoe UI, Arial, sans-serif;
    }
    .browser {
      background: #dbe2ea;
      border-bottom: 1px solid #cbd5e1;
      padding: 10px 14px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .window-title {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
      font-weight: 700;
    }
    .title-stack {
      display: grid;
      gap: 2px;
    }
    .app-subtitle {
      color: #475569;
      font-size: 12px;
      font-weight: 700;
    }
    .dots span { font-size: 13px; margin-right: 4px; }
    .bar {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 10px;
      align-items: center;
      background: #eef2f7;
      padding: 8px;
      margin-top: 8px;
    }
    .nav { display: flex; gap: 6px; }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      min-height: 36px;
      padding: 0 14px;
      border-radius: 6px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      background: var(--blue);
      color: #fff;
      border-color: var(--blue);
    }
    button:disabled {
      opacity: .6;
      cursor: wait;
    }
    .address {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      height: 38px;
      padding: 0 12px;
    }
    .address input {
      width: 100%;
      border: 0;
      outline: 0;
      font-size: 14px;
      color: var(--text);
    }
    main {
      padding: 18px;
      max-width: 1440px;
      margin: 0 auto;
    }
    .tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 14px;
      overflow-x: auto;
    }
    .tabs button.active {
      background: #fff;
      border-color: var(--blue);
      color: var(--blue);
    }
    .summary-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 10px;
      margin: 12px 0 14px;
    }
    .summary-item {
      background: #fff;
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 8px;
      padding: 12px;
      min-width: 0;
    }
    .summary-item strong {
      display: block;
      margin-top: 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .flow-board {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .flow-board h2 {
      margin: 0 0 12px;
      font-size: 16px;
    }
    .flow-steps {
      display: grid;
      grid-template-columns: repeat(6, minmax(130px, 1fr));
      gap: 8px;
    }
    .flow-step {
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #f8fafc;
      padding: 10px;
      min-width: 0;
      cursor: pointer;
    }
    .flow-step.active {
      border-color: var(--blue);
      background: #eff6ff;
    }
    .flow-number {
      width: 24px;
      height: 24px;
      display: inline-grid;
      place-items: center;
      border-radius: 999px;
      background: var(--blue);
      color: #fff;
      font-weight: 800;
      font-size: 12px;
      margin-bottom: 8px;
    }
    .flow-title {
      font-weight: 800;
      font-size: 13px;
      margin-bottom: 4px;
    }
    .flow-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .card h2, .card h3 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    .metric-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .metric-value {
      margin-top: 8px;
      font-size: 28px;
      font-weight: 800;
    }
    .metric-sub {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-top: 6px;
    }
    .layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-top: 14px;
    }
    .status {
      padding: 12px 14px;
      border-radius: 6px;
      background: #e0f2fe;
      color: #0369a1;
      font-weight: 700;
      margin: 12px 0;
    }
    .status.running { background: #fef3c7; color: #92400e; }
    .status.success { background: #d1fae5; color: #065f46; }
    .status.error { background: #fee2e2; color: #991b1b; }
    .scraper-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, .8fr);
      gap: 14px;
      align-items: start;
    }
    .log-panel {
      background: #0f172a;
      color: #dbeafe;
      border: 1px solid #1e293b;
      border-radius: 8px;
      min-height: 280px;
      max-height: 520px;
      overflow: auto;
      padding: 14px;
      font-family: Consolas, Menlo, monospace;
      font-size: 13px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    .log-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .form-row {
      display: grid;
      grid-template-columns: 1fr 120px auto auto;
      gap: 10px;
      align-items: center;
    }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .toolbar h2 {
      margin: 0;
      font-size: 16px;
    }
    .toolbar-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: min(420px, 100%);
    }
    input[type="text"], input[type="number"], input[type="search"] {
      border: 1px solid var(--line);
      border-radius: 6px;
      min-height: 38px;
      padding: 0 12px;
      font-size: 14px;
      width: 100%;
    }
    label.check {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-weight: 700;
      white-space: nowrap;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .table-wrap {
      overflow: auto;
      border-radius: 8px;
    }
    th, td {
      border-bottom: 1px solid #e5e7eb;
      padding: 10px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }
    th {
      background: #f8fafc;
      font-size: 12px;
      text-transform: uppercase;
      color: var(--muted);
    }
    .bar-line {
      display: grid;
      grid-template-columns: 110px 1fr 60px;
      gap: 10px;
      align-items: center;
      margin: 10px 0;
    }
    .nlp-list {
      display: grid;
      gap: 12px;
    }
    .nlp-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .nlp-review {
      display: grid;
      grid-template-columns: minmax(220px, .9fr) minmax(0, 1.6fr);
      gap: 14px;
    }
    .nlp-pipeline {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .nlp-stage {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #f8fafc;
      min-width: 0;
    }
    .nlp-stage h3 {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 0 0 8px;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
    }
    .help {
      position: relative;
      display: inline-grid;
      place-items: center;
      width: 18px;
      height: 18px;
      border-radius: 999px;
      border: 1px solid #94a3b8;
      background: #fff;
      color: #475569;
      font-size: 11px;
      font-weight: 900;
      cursor: help;
      text-transform: none;
    }
    .help:hover::after, .help:focus::after {
      content: attr(data-tip);
      position: absolute;
      left: 50%;
      bottom: calc(100% + 8px);
      transform: translateX(-50%);
      width: min(260px, 70vw);
      background: #111827;
      color: #fff;
      border-radius: 8px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.4;
      font-weight: 700;
      text-transform: none;
      z-index: 20;
      box-shadow: 0 8px 18px rgba(15, 23, 42, .24);
    }
    .help:hover::before, .help:focus::before {
      content: "";
      position: absolute;
      left: 50%;
      bottom: calc(100% + 2px);
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #111827;
      z-index: 21;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      border: 1px solid #cbd5e1;
      background: #fff;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      line-height: 1.2;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    .chip.strong {
      border-color: #bfdbfe;
      background: #eff6ff;
      color: #1d4ed8;
      font-weight: 800;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 800;
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
      white-space: nowrap;
    }
    .pill.positive { background: #dcfce7; color: #166534; border-color: #86efac; }
    .pill.negative { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
    .pill.neutral { background: #e0f2fe; color: #075985; border-color: #bae6fd; }
    .vector-table {
      width: 100%;
      margin-top: 8px;
      table-layout: fixed;
    }
    .vector-table th, .vector-table td {
      padding: 6px;
      font-size: 12px;
      text-align: center;
      overflow-wrap: anywhere;
    }
    .vector-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
      gap: 6px;
      margin-top: 10px;
      max-height: 220px;
      overflow: auto;
      padding-right: 2px;
    }
    .vector-cell {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 6px;
      border: 1px solid #dbe3ee;
      background: #fff;
      border-radius: 6px;
      padding: 6px 7px;
      min-width: 0;
      font-size: 12px;
    }
    .vector-cell.zero {
      color: #94a3b8;
      background: #f8fafc;
    }
    .vector-term {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 700;
    }
    .vector-value {
      min-width: 22px;
      height: 22px;
      display: inline-grid;
      place-items: center;
      border-radius: 999px;
      background: #dbeafe;
      color: #1d4ed8;
      font-weight: 900;
    }
    .vector-cell.zero .vector-value {
      background: #e5e7eb;
      color: #64748b;
    }
    .review-text {
      font-weight: 700;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .empty-state {
      border: 1px dashed #94a3b8;
      border-radius: 8px;
      padding: 24px;
      color: var(--muted);
      background: #fff;
      font-weight: 700;
      text-align: center;
    }
    .track {
      background: #e5e7eb;
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: var(--blue);
    }
    .hidden { display: none; }
    @media (max-width: 900px) {
      .bar, .form-row, .layout, .grid, .scraper-grid, .nlp-review, .nlp-pipeline, .nlp-summary, .summary-strip, .flow-steps { grid-template-columns: 1fr; }
      .toolbar { align-items: stretch; flex-direction: column; }
      .actions, .nav { flex-wrap: wrap; }
    }
  </style>
</head>
<body>
  <header class="browser">
    <div class="window-title">
      <div class="dots"><span style="color:#ef4444">●</span><span style="color:#f59e0b">●</span><span style="color:#10b981">●</span></div>
      <div class="title-stack">
        <div>Tokopedia Review Analytics</div>
        <div class="app-subtitle">Scraping, sentimen, dan pipeline NLP</div>
      </div>
    </div>
    <div class="bar">
      <div class="nav">
        <button onclick="showTab('overview')">←</button>
        <button onclick="showTab('data')">→</button>
        <button onclick="loadData()">↻</button>
      </div>
      <div class="address">
        <span style="color:var(--green);font-weight:800">🔒</span>
        <input id="routeInput" value="tokopedia://dashboard/ringkasan" onkeydown="routeKey(event)">
      </div>
      <div class="actions">
        <button onclick="showTab('scraper')">Ambil Data</button>
        <button onclick="showTab('nlp')">NLP</button>
        <button class="primary" onclick="loadData()">Segarkan</button>
      </div>
    </div>
  </header>

  <main>
    <nav class="tabs">
      <button data-tab="overview" onclick="showTab('overview')" class="active">1 Ringkasan</button>
      <button data-tab="scraper" onclick="showTab('scraper')">2 Scraping</button>
      <button data-tab="data" onclick="showTab('data')">3 Data Mentah</button>
      <button data-tab="nlp" onclick="showTab('nlp')">4 NLP</button>
      <button data-tab="rating" onclick="showTab('rating')">5 Rating</button>
      <button data-tab="sentiment" onclick="showTab('sentiment')">6 Sentimen</button>
    </nav>

    <section id="overview" class="page">
      <div id="quality" class="status">Memuat dataset...</div>
      <div class="flow-board">
        <h2>Alur Project</h2>
        <div class="flow-steps" id="flowSteps"></div>
      </div>
      <div class="summary-strip" id="summaryStrip"></div>
      <div class="grid" id="metrics"></div>
      <div class="layout">
        <div class="card">
          <h2>Distribusi Sentimen</h2>
          <div id="sentimentBars"></div>
        </div>
        <div class="card">
          <h2>Distribusi Rating</h2>
          <div id="ratingBars"></div>
        </div>
      </div>
    </section>

    <section id="scraper" class="page hidden">
      <div class="scraper-grid">
        <div class="card">
          <h2>Browser Scraper Tokopedia</h2>
          <div class="form-row">
            <input id="scrapeUrl" type="text" placeholder="https://www.tokopedia.com/nama-toko/nama-produk">
            <input id="maxReviews" type="number" min="1" max="1000" value="100">
            <label class="check"><input id="useCache" type="checkbox"> Pakai cache</label>
            <label class="check"><input id="showBrowser" type="checkbox"> Browser visual</label>
          </div>
          <div id="scrapeStatus" class="status">Siap mengambil data.</div>
          <button id="scrapeButton" class="primary" onclick="startScrape()">Mulai Ambil Data</button>
        </div>
        <div class="card">
          <div class="log-title">
            <h2>Log Tahapan Scraping</h2>
            <button onclick="clearLogView()">Bersihkan</button>
          </div>
          <div id="scrapeLog" class="log-panel">Menunggu proses scraping...</div>
        </div>
      </div>
    </section>

    <section id="sentiment" class="page hidden">
      <div class="card">
        <h2>Analisis Sentimen</h2>
        <div id="sentimentDetail"></div>
      </div>
    </section>

    <section id="rating" class="page hidden">
      <div class="card">
        <h2>Analisis Rating</h2>
        <div id="ratingDetail"></div>
      </div>
    </section>

    <section id="nlp" class="page hidden">
      <div id="nlpSummary" class="nlp-summary"></div>
      <div id="nlpFlowExample" class="flow-board"></div>
      <div class="nlp-list" id="nlpRows"></div>
    </section>

    <section id="data" class="page hidden">
      <div class="toolbar">
        <h2>Tabel Data Ulasan</h2>
        <div class="toolbar-actions">
          <input id="tableSearch" type="search" placeholder="Cari review, sentimen, atau token..." oninput="renderRows()">
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Review</th><th>Rating</th><th>Sentimen</th><th>Panjang</th><th>Sumber</th><th>Tanggal</th></tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    let dataset = [];
    const flow = [
      {tab:'overview', title:'Ringkasan', note:'Lihat status dataset dan gambaran hasil.'},
      {tab:'scraper', title:'Scraping', note:'Ambil ulasan real dari halaman Tokopedia.'},
      {tab:'data', title:'Data Mentah', note:'Cek teks review, rating, sumber, dan tanggal.'},
      {tab:'nlp', title:'Preprocessing NLP', note:'Tokenization, stopword removal, stemming, vectorization.'},
      {tab:'rating', title:'Rating', note:'Distribusi nilai bintang dari ulasan.'},
      {tab:'sentiment', title:'Sentimen', note:'Klasifikasi positive, neutral, negative.'},
    ];

    function showTab(name) {
      document.querySelectorAll('.page').forEach(el => el.classList.add('hidden'));
      document.getElementById(name).classList.remove('hidden');
      document.querySelectorAll('.tabs button').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
      const routes = {overview:'ringkasan', scraper:'ambil-data', sentiment:'sentimen', rating:'rating', nlp:'nlp', data:'data'};
      document.getElementById('routeInput').value = `tokopedia://dashboard/${routes[name] || name}`;
      renderFlow(name);
    }

    function routeKey(event) {
      if (event.key !== 'Enter') return;
      const value = event.target.value.toLowerCase();
      if (value.includes('ambil') || value.includes('scraper')) return showTab('scraper');
      if (value.includes('sentimen') || value.includes('sentiment')) return showTab('sentiment');
      if (value.includes('rating')) return showTab('rating');
      if (value.includes('nlp') || value.includes('token') || value.includes('stemming') || value.includes('vector')) return showTab('nlp');
      if (value.includes('data') || value.includes('tabel')) return showTab('data');
      showTab('overview');
    }

    function countBy(key) {
      return dataset.reduce((acc, row) => {
        const value = String(row[key] ?? 'unknown').toLowerCase();
        acc[value] = (acc[value] || 0) + 1;
        return acc;
      }, {});
    }

    function nlpStats() {
      const vocabulary = new Set();
      let tokenCount = 0;
      let stemCount = 0;
      let vectorCells = 0;
      dataset.forEach(row => {
        asArray(row.nlp_tokens).forEach(() => tokenCount += 1);
        asArray(row.nlp_stems).forEach(term => {
          stemCount += 1;
          vocabulary.add(String(term));
        });
        asArray(row.vector_values).forEach(value => {
          if (Number(value) > 0) vectorCells += 1;
        });
      });
      return {
        vocabulary: Array.from(vocabulary).filter(Boolean),
        tokenCount,
        stemCount,
        vectorCells,
        avgTokens: dataset.length ? (tokenCount / dataset.length).toFixed(1) : '-'
      };
    }

    function sentimentPill(value) {
      const label = String(value || 'neutral').toLowerCase();
      return `<span class="pill ${escapeHtml(label)}">${escapeHtml(label)}</span>`;
    }

    function renderFlow(active = 'overview') {
      const el = document.getElementById('flowSteps');
      if (!el) return;
      el.innerHTML = flow.map((step, index) => `
        <div class="flow-step ${step.tab === active ? 'active' : ''}" onclick="showTab('${step.tab}')">
          <div class="flow-number">${index + 1}</div>
          <div class="flow-title">${escapeHtml(step.title)}</div>
          <div class="flow-note">${escapeHtml(step.note)}</div>
        </div>
      `).join('');
    }

    function barHtml(items, color) {
      const max = Math.max(1, ...Object.values(items));
      return Object.entries(items).map(([label, count]) => `
        <div class="bar-line">
          <strong>${label}</strong>
          <div class="track"><div class="fill" style="width:${count / max * 100}%;background:${color}"></div></div>
          <span>${count}</span>
        </div>
      `).join('');
    }

    function asArray(value) {
      if (Array.isArray(value)) return value;
      if (value === null || value === undefined || value === '') return [];
      return [value];
    }

    function chipsHtml(values) {
      const items = asArray(values);
      if (!items.length) return '<span class="chip">-</span>';
      return items.map(item => `<span class="chip">${escapeHtml(String(item))}</span>`).join('');
    }

    function objectChipsHtml(value) {
      const obj = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
      const entries = Object.entries(obj);
      if (!entries.length) return '<span class="chip">-</span>';
      return entries.map(([key, count]) => `<span class="chip">${escapeHtml(String(key))}: ${escapeHtml(String(count))}</span>`).join('');
    }

    function stageTitle(label, tip) {
      return `${escapeHtml(label)} <span class="help" tabindex="0" data-tip="${escapeHtml(tip)}">?</span>`;
    }

    function vectorHtml(row) {
      const terms = asArray(row.vector_terms);
      const values = asArray(row.vector_values);
      if (!terms.length) return '<div class="chips"><span class="chip">-</span></div>';
      return `
        <div class="vector-grid">
          ${terms.map((term, index) => {
            const value = Number(values[index] ?? 0);
            return `
              <div class="vector-cell ${value ? '' : 'zero'}" title="${escapeHtml(String(term))}: ${escapeHtml(String(value))}">
                <span class="vector-term">${escapeHtml(String(term))}</span>
                <span class="vector-value">${escapeHtml(String(value))}</span>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    function renderSummary(stats) {
      const nlp = nlpStats();
      const sources = [...new Set(dataset.map(row => row.source).filter(Boolean))];
      const dates = dataset.map(row => row.date_scraped).filter(Boolean).sort();
      const latestDate = dates.length ? dates[dates.length - 1] : '-';
      document.getElementById('summaryStrip').innerHTML = [
        ['Sumber Data', sources.join(', ') || '-', 'var(--blue)'],
        ['Update Terakhir', latestDate, 'var(--green)'],
        ['Vocabulary NLP', `${nlp.vocabulary.length} term`, 'var(--violet)'],
        ['Rata Token', `${nlp.avgTokens} token/ulasan`, 'var(--amber)'],
      ].map(([label, value, color]) => `
        <div class="summary-item" style="border-left-color:${color}">
          <div class="metric-label">${label}</div>
          <strong>${escapeHtml(String(value))}</strong>
        </div>
      `).join('');
    }

    function renderRows() {
      const query = String(document.getElementById('tableSearch')?.value || '').toLowerCase();
      const rows = dataset.filter(row => {
        const haystack = [
          row.review_text,
          row.sentiment,
          row.source,
          ...asArray(row.nlp_tokens),
          ...asArray(row.nlp_stems),
          ...asArray(row.vector_terms)
        ].join(' ').toLowerCase();
        return !query || haystack.includes(query);
      });

      document.getElementById('rows').innerHTML = rows.map(row => `
        <tr>
          <td>${row.id ?? ''}</td>
          <td>${escapeHtml(String(row.review_text ?? '')).slice(0, 260)}</td>
          <td><span class="pill">${escapeHtml(String(row.rating ?? 0))}</span></td>
          <td>${sentimentPill(row.sentiment)}</td>
          <td>${row.text_length ?? ''}</td>
          <td>${escapeHtml(String(row.source ?? '-'))}</td>
          <td>${escapeHtml(String(row.date_scraped ?? '-'))}</td>
        </tr>
      `).join('') || '<tr><td colspan="7"><div class="empty-state">Tidak ada baris yang cocok.</div></td></tr>';
    }

    function renderNlp() {
      const el = document.getElementById('nlpRows');
      if (!dataset.length) {
        document.getElementById('nlpSummary').innerHTML = '';
        document.getElementById('nlpFlowExample').innerHTML = '';
        el.innerHTML = '<div class="status error">Dataset belum berisi ulasan.</div>';
        return;
      }

      const stats = nlpStats();
      document.getElementById('nlpSummary').innerHTML = [
        ['Total Token', stats.tokenCount, 'var(--blue)'],
        ['Total Stem', stats.stemCount, 'var(--green)'],
        ['Vocabulary', stats.vocabulary.length, 'var(--violet)'],
        ['Vector Aktif', stats.vectorCells, 'var(--amber)'],
      ].map(([label, value, color]) => `
        <div class="card">
          <div class="metric-label">${label}</div>
          <div class="metric-value" style="color:${color}">${value}</div>
          <div class="metric-sub">${label === 'Vocabulary' ? stats.vocabulary.slice(0, 6).join(', ') || '-' : 'Corpus hasil scraping'}</div>
        </div>
      `).join('');

      const sample = dataset[0] || {};
      document.getElementById('nlpFlowExample').innerHTML = `
        <h2>Contoh Alur NLP dari Satu Ulasan</h2>
        <div class="flow-steps">
          <div class="flow-step">
            <div class="flow-number">0</div>
            <div class="flow-title">Data Review</div>
            <div class="flow-note">${escapeHtml(String(sample.review_text || '-')).slice(0, 120)}</div>
          </div>
          <div class="flow-step">
            <div class="flow-number">1</div>
            <div class="flow-title">Tokenization <span class="help" tabindex="0" data-tip="Memecah teks menjadi token/kata.">?</span></div>
            <div class="flow-note">${escapeHtml(asArray(sample.nlp_tokens).slice(0, 8).map(String).join(', ') || '-')}</div>
          </div>
          <div class="flow-step">
            <div class="flow-number">2</div>
            <div class="flow-title">Stopword Removal <span class="help" tabindex="0" data-tip="Menghapus kata umum agar analisis fokus pada kata penting.">?</span></div>
            <div class="flow-note">${escapeHtml(asArray(sample.nlp_no_stopwords).slice(0, 8).map(String).join(', ') || '-')}</div>
          </div>
          <div class="flow-step">
            <div class="flow-number">3</div>
            <div class="flow-title">Stemming <span class="help" tabindex="0" data-tip="Mengubah token ke bentuk kata dasar.">?</span></div>
            <div class="flow-note">${escapeHtml(asArray(sample.nlp_stems).slice(0, 8).map(String).join(', ') || '-')}</div>
          </div>
          <div class="flow-step">
            <div class="flow-number">4</div>
            <div class="flow-title">Vectorization <span class="help" tabindex="0" data-tip="Mengubah term menjadi fitur numerik untuk analisis.">?</span></div>
            <div class="flow-note">${escapeHtml(asArray(sample.vector_terms).slice(0, 6).map((term, i) => `${term}:${asArray(sample.vector_values)[i] ?? 0}`).join(', ') || '-')}</div>
          </div>
          <div class="flow-step">
            <div class="flow-number">5</div>
            <div class="flow-title">Output</div>
            <div class="flow-note">${escapeHtml(`Sentimen ${String(sample.sentiment || '-')} · Rating ${String(sample.rating ?? '-')}`)}</div>
          </div>
        </div>
      `;

      el.innerHTML = dataset.map(row => `
        <div class="card nlp-review">
          <div>
            <div class="metric-label">Ulasan #${escapeHtml(String(row.id ?? ''))}</div>
            <div class="review-text">${escapeHtml(String(row.review_text ?? ''))}</div>
            <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
              <span class="pill">Rating ${escapeHtml(String(row.rating ?? 0))}</span>
              ${sentimentPill(row.sentiment)}
              <span class="pill">${escapeHtml(String(row.text_length ?? 0))} karakter</span>
            </div>
          </div>
          <div class="nlp-pipeline">
            <div class="nlp-stage">
              <h3>${stageTitle('Tokenization', 'Memecah teks ulasan menjadi token/kata agar bisa diproses sebagai data NLP.')}</h3>
              <div class="chips">${chipsHtml(row.nlp_tokens)}</div>
            </div>
            <div class="nlp-stage">
              <h3>${stageTitle('Stopword Removal', 'Menghapus kata umum seperti yang, dan, di, ke agar kata bermakna lebih dominan.')}</h3>
              <div class="chips">${chipsHtml(row.nlp_no_stopwords)}</div>
            </div>
            <div class="nlp-stage">
              <h3>${stageTitle('Stemming', 'Mengubah kata ke bentuk dasar, misalnya produknya menjadi produk atau memuaskan menjadi puas.')}</h3>
              <div class="chips">${chipsHtml(row.nlp_stems)}</div>
            </div>
            <div class="nlp-stage">
              <h3>${stageTitle('Vectorization', 'Mengubah kata hasil stemming menjadi angka. Setiap term menjadi fitur, nilainya menunjukkan frekuensi term pada ulasan.')}</h3>
              <div class="chips">${objectChipsHtml(row.nlp_term_frequency)}</div>
              ${vectorHtml(row)}
            </div>
          </div>
        </div>
      `).join('');
    }

    function render(data) {
      dataset = data.rows || [];
      const stats = data.stats || {};
      const quality = document.getElementById('quality');
      quality.textContent = data.message || 'Dataset dimuat.';
      quality.className = `status ${dataset.length ? 'success' : 'error'}`;
      renderSummary(stats);

      document.getElementById('metrics').innerHTML = [
        ['Total Ulasan', stats.total_reviews ?? 0, 'var(--blue)'],
        ['Rata Rating', stats.avg_rating ?? '-', 'var(--amber)'],
        ['Positif', stats.positive ?? 0, 'var(--green)'],
        ['Negatif', stats.negative ?? 0, 'var(--red)'],
        ['Netral', stats.neutral ?? 0, 'var(--cyan)'],
        ['Rata Teks', stats.avg_text_length ?? '-', 'var(--muted)'],
        ['Rating Max', stats.max_rating ?? '-', 'var(--green)'],
        ['Rating Min', stats.min_rating ?? '-', 'var(--red)'],
      ].map(([label, value, color]) => `
        <div class="card"><div class="metric-label">${label}</div><div class="metric-value" style="color:${color}">${value}</div></div>
      `).join('');

      const sentiments = countBy('sentiment');
      const ratings = countBy('rating');
      document.getElementById('sentimentBars').innerHTML = barHtml(sentiments, 'var(--green)');
      document.getElementById('ratingBars').innerHTML = barHtml(ratings, 'var(--amber)');
      document.getElementById('sentimentDetail').innerHTML = barHtml(sentiments, 'var(--blue)');
      document.getElementById('ratingDetail').innerHTML = barHtml(ratings, 'var(--amber)');
      renderNlp();
      renderRows();
      renderFlow(document.querySelector('.tabs button.active')?.dataset.tab || 'overview');
    }

    function escapeHtml(text) {
      return text.replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }

    async function loadData() {
      const response = await fetch('/api/data');
      render(await response.json());
    }

    async function startScrape() {
      const url = document.getElementById('scrapeUrl').value.trim();
      if (!url) {
        alert('Masukkan URL produk Tokopedia.');
        return;
      }
      const button = document.getElementById('scrapeButton');
      button.disabled = true;
      document.getElementById('scrapeLog').textContent = 'Memulai worker scraping...';
      await fetch('/api/scrape', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          url,
          max_reviews: Number(document.getElementById('maxReviews').value || 100),
          use_cache: document.getElementById('useCache').checked,
          headless: !document.getElementById('showBrowser').checked
        })
      });
      pollStatus();
    }

    function renderScrapeLog(logs) {
      const panel = document.getElementById('scrapeLog');
      const text = (logs && logs.length) ? logs.join('\n') : 'Belum ada log.';
      const shouldStick = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 24;
      panel.textContent = text;
      if (shouldStick) panel.scrollTop = panel.scrollHeight;
    }

    function clearLogView() {
      document.getElementById('scrapeLog').textContent = '';
    }

    async function pollStatus() {
      const response = await fetch('/api/status');
      const status = await response.json();
      const el = document.getElementById('scrapeStatus');
      el.textContent = status.message;
      el.className = `status ${status.running ? 'running' : status.success ? 'success' : status.success === false ? 'error' : ''}`;
      renderScrapeLog(status.logs || []);
      document.getElementById('scrapeButton').disabled = status.running;
      if (status.running) {
        setTimeout(pollStatus, 1500);
      } else {
        loadData();
      }
    }

    loadData();
    pollStatus();
  </script>
</body>
</html>
"""


def load_dataset():
    if not CSV_FILE.exists():
        return {
            "message": "Dataset lokal belum ada. Jalankan scraper dari tab Ambil Data.",
            "rows": [],
            "stats": {},
        }

    with CSV_FILE.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    for index, row in enumerate(rows, start=1):
        row.setdefault("id", index)
        row["review_text"] = str(row.get("review_text") or "")
        try:
            row["rating"] = int(float(row.get("rating") or 0))
        except ValueError:
            row["rating"] = 0
        row["sentiment"] = str(row.get("sentiment") or "neutral").lower()
        try:
            row["text_length"] = int(float(row.get("text_length") or len(row["review_text"])))
        except ValueError:
            row["text_length"] = len(row["review_text"])
        row["nlp_tokens"] = parse_literal(row.get("nlp_tokens"), [])
        row["nlp_no_stopwords"] = parse_literal(row.get("nlp_no_stopwords"), [])
        row["nlp_stems"] = parse_literal(row.get("nlp_stems"), [])
        row["nlp_term_frequency"] = parse_literal(row.get("nlp_term_frequency"), {})
        row["vector_terms"] = parse_literal(row.get("vector_terms"), [])
        row["vector_values"] = parse_literal(row.get("vector_values"), [])

    valid_ratings = [row["rating"] for row in rows if 1 <= row["rating"] <= 5]
    text_lengths = [row["text_length"] for row in rows]
    sentiments = [row["sentiment"] for row in rows]

    stats = {
        "total_reviews": len(rows),
        "avg_rating": f"{sum(valid_ratings) / len(valid_ratings):.1f}" if valid_ratings else "-",
        "positive": sentiments.count("positive"),
        "negative": sentiments.count("negative"),
        "neutral": sentiments.count("neutral"),
        "avg_text_length": f"{sum(text_lengths) / len(text_lengths):.0f}" if text_lengths else "-",
        "max_rating": max(valid_ratings) if valid_ratings else "-",
        "min_rating": min(valid_ratings) if valid_ratings else "-",
    }

    return {
        "message": f"Dataset dimuat: {len(rows)} ulasan.",
        "rows": rows,
        "stats": stats,
    }


def run_scrape_worker(options):
    forced_headless = False
    if not options["headless"] and not can_launch_headed_browser():
        options = dict(options)
        options["headless"] = True
        forced_headless = True

    with scrape_state_lock:
        scrape_state.update({
            "running": True,
            "success": None,
            "message": "Browser scraper sedang berjalan...",
            "count": 0,
            "logs": [],
        })

    append_scrape_log("Worker dimulai.")
    if forced_headless:
        append_scrape_log("Browser visual tidak tersedia di environment ini. Mode diubah ke headless.")
    append_scrape_log(f"URL target: {options['url']}")
    append_scrape_log(f"Maksimal ulasan: {options['max_reviews']}")
    append_scrape_log(f"Cache: {'aktif' if options['use_cache'] else 'nonaktif'}")
    append_scrape_log(f"Mode browser: {'headless' if options['headless'] else 'visual Chromium'}")

    log_handler = ScrapeLogHandler()
    log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)
    try:
        append_scrape_log("Memuat modul scraper.")
        try:
            from scraper_ecomm_advanced import scrape_reviews_advanced, save_to_csv, save_to_json
        except ModuleNotFoundError as exc:
            package = exc.name or str(exc)
            message = f"Dependency Python belum terpasang: {package}. Jalankan: pip install -r requirements_final.txt"
            append_scrape_log(f"ERROR: {message}")
            with scrape_state_lock:
                scrape_state.update({"running": False, "success": False, "message": message, "count": 0})
            return

        async def run_with_timeout():
            return await asyncio.wait_for(
                scrape_reviews_advanced(**options),
                timeout=SCRAPE_TIMEOUT_SECONDS,
            )

        append_scrape_log("Menjalankan proses scraping.")
        data = asyncio.run(run_with_timeout())
        if not data:
            append_scrape_log("Selesai tanpa ulasan valid.")
            with scrape_state_lock:
                scrape_state.update({"running": False, "success": False, "message": "Tidak ada ulasan valid yang berhasil diekstrak.", "count": 0})
            return

        append_scrape_log(f"Menyimpan {len(data)} ulasan ke CSV.")
        save_to_csv(data, str(CSV_FILE))
        append_scrape_log("Menyimpan hasil ke JSON.")
        save_to_json(data, str(JSON_FILE))
        append_scrape_log("Dashboard siap memuat dataset terbaru.")
        with scrape_state_lock:
            scrape_state.update({"running": False, "success": True, "message": f"Selesai. {len(data)} ulasan disimpan.", "count": len(data)})
    except TimeoutError:
        message = (
            "Scraping timeout. Target Tokopedia terlalu lama merespons dari environment ini. "
            "Coba URL produk langsung www.tokopedia.com, turunkan jumlah ulasan, atau coba lagi nanti."
        )
        append_scrape_log(f"ERROR: {message}")
        with scrape_state_lock:
            scrape_state.update({"running": False, "success": False, "message": message, "count": 0})
    except Exception as exc:
        append_scrape_log(f"ERROR: {exc}")
        with scrape_state_lock:
            scrape_state.update({"running": False, "success": False, "message": f"Gagal mengambil data: {exc}", "count": 0})
    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(previous_level)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/data":
            self.send_json(load_dataset())
            return
        if path == "/api/status":
            with scrape_state_lock:
                self.send_json(dict(scrape_state))
            return

        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = urlparse(self.path).path
        content_type = "application/json; charset=utf-8" if path.startswith("/api/") else "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/scrape":
            self.send_json({"error": "Not found"}, status=404)
            return
        with scrape_state_lock:
            is_running = scrape_state["running"]
        if is_running:
            self.send_json({"error": "Scraper masih berjalan."}, status=409)
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        url = str(payload.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            self.send_json({"error": "URL harus diawali http:// atau https://."}, status=400)
            return

        options = {
            "url": url,
            "max_reviews": int(payload.get("max_reviews") or 100),
            "use_cache": bool(payload.get("use_cache")),
            "headless": bool(payload.get("headless")) or not can_launch_headed_browser(),
        }
        thread = threading.Thread(target=run_scrape_worker, args=(options,), daemon=True)
        thread.start()
        self.send_json({"ok": True, "message": "Scraper dimulai."})


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard browser berjalan di http://{DISPLAY_HOST}:{PORT}")
    print("Tekan Ctrl+C untuk berhenti.")
    server.serve_forever()


if __name__ == "__main__":
    main()
