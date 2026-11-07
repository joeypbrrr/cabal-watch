/* Cabal Watch dashboard. Reads JSON only. Never signs or sends a transaction. */
(function () {
  const FILES = ["wallets", "funding", "transactions", "alerts", "paper", "bubbles", "early_buys"];
  const PAGE_MS = 60000;
  const COGE = "8UQdy5sHMVWUWSHeA5B3ZuuAVNumjSLPXdf19MXcpump";
  const DEMOCAT = "9Y1F6dZ6HpjZDYZdYuUGwMbkUiPsyU7WPTqTQU4Tpump";
  const CLAIM = { wallets: 63, cogePct: 44.65, source: "Owner screenshot IMG_4522.png, Bubblemaps Cluster 1" };
  const B58 = /^[1-9A-HJ-NP-Za-km-z]{32,88}$/;
  const ROLE = {
    screenshot_matched_coge_holder: "Screenshot match",
    token_holder: "Holder, not confirmed",
    deployer: "Deployer",
    largest_first_10s_buyer: "Large buyer in the first 10 seconds",
    exchange_or_service: "Exchange or service",
    unlabeled_busy_funder: "Busy wallet, not the cabal funder",
  };

  const state = {
    docs: {},
    sources: {},
    walletView: "watched",
    txWallet: "all",
    bubble: "coge",
    launchMint: null,
    selected: null,
    sims: [],
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function isNum(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function formatET(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    const formatted = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(date);
    return formatted + " ET";
  }

  function formatPct(value) {
    if (!isNum(value)) return "—";
    return value.toLocaleString("en-US", { maximumFractionDigits: 2 }) + "%";
  }

  function formatUsd(value) {
    if (!isNum(value)) return "—";
    return value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  }

  function formatSol(value) {
    if (!isNum(value)) return "—";
    return value.toLocaleString("en-US", { maximumFractionDigits: 4 }) + " SOL";
  }

  function formatPnl(value) {
    if (!isNum(value)) return "—";
    const sign = value > 0 ? "+" : "";
    return sign + value.toLocaleString("en-US", { maximumFractionDigits: 1 }) + "%";
  }

  function short(value) {
    const text = String(value || "");
    if (text.length < 12) return text;
    return text.slice(0, 4) + "…" + text.slice(-4);
  }

  function safeUrl(address, prefix) {
    return B58.test(address) ? prefix + address : null;
  }

  function link(href, label) {
    if (!href || !/^https:\/\//.test(href)) return "";
    return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  }

  function accountLinks(address) {
    return [
      link(safeUrl(address, "https://solscan.io/account/"), "Solscan"),
      link(safeUrl(address, "https://gmgn.ai/sol/address/"), "GMGN"),
    ].filter(Boolean).join("");
  }

  function dexLink(mint) {
    return link(safeUrl(mint, "https://dexscreener.com/solana/"), "DexScreener");
  }

  function wallets() {
    return (state.docs.wallets && state.docs.wallets.wallets) || [];
  }

  function walletMap() {
    return new Map(wallets().map((wallet) => [wallet.address, wallet]));
  }

  function labelFor(address, map) {
    const wallet = (map || walletMap()).get(address);
    if (wallet && wallet.label) return wallet.label;
    return short(address);
  }

  function isExchange(address, map) {
    const wallet = (map || walletMap()).get(address);
    if (!wallet) return false;
    return wallet.role === "exchange_or_service" || wallet.role === "unlabeled_busy_funder";
  }

  function isMatched(wallet) {
    return wallet.role === "screenshot_matched_coge_holder" || wallet.reported_cluster_id === "coge-screenshot-1";
  }

  function newestStamp() {
    let best = null;
    FILES.forEach((name) => {
      const doc = state.docs[name];
      const stamp = doc && doc.updated_at;
      if (!stamp) return;
      const time = new Date(stamp).getTime();
      if (!best || time > best.time) best = { time, stamp, name };
    });
    return best;
  }

  async function fetchJson(url) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return null;
      return JSON.parse(await response.text());
    } catch (err) {
      return null;
    }
  }

  async function loadAll() {
    const bust = Date.now();
    await Promise.all(FILES.map(async (name) => {
      const live = await fetchJson(`data/${name}.json?t=${bust}`);
      if (live && typeof live === "object") {
        state.docs[name] = live;
        state.sources[name] = "live";
        return;
      }
      const sample = await fetchJson(`data/sample/${name}.json?t=${bust}`);
      if (sample && typeof sample === "object") {
        state.docs[name] = sample;
        state.sources[name] = "sample";
        return;
      }
      state.docs[name] = null;
      state.sources[name] = "missing";
    }));
  }

  function banner() {
    const host = $("banner");
    const example = FILES.filter((name) => {
      const doc = state.docs[name];
      return state.sources[name] === "sample" || (doc && (doc.example === true || doc.status === "example"));
    });
    const snapshot = FILES.filter((name) => state.docs[name] && state.docs[name].status === "snapshot_only_monitor_not_running");
    host.classList.remove("example");
    if (example.length) {
      host.hidden = false;
      host.classList.add("example");
      host.textContent = "Example data. These figures are fictional sample files for the layout. They are not the research snapshot and not live wallets.";
      return;
    }
    if (snapshot.length === FILES.length) {
      host.hidden = false;
      host.textContent = "Saved snapshot. The monitor was not running when these files were written. Empty trades, alerts, and paper rows mean this file has none, not that the wallets were idle.";
      return;
    }
    if (snapshot.length) {
      host.hidden = false;
      host.textContent = "Some files are still the saved snapshot: " + snapshot.map((name) => name + ".json").join(", ") + ".";
      return;
    }
    host.hidden = true;
    host.textContent = "";
  }

  function renderSummary() {
    const map = walletMap();
    const matched = wallets().filter(isMatched);
    let held = 0;
    let heldKnown = false;
    matched.forEach((wallet) => {
      (wallet.tokens || []).forEach((token) => {
        if (token.mint === COGE && isNum(token.pct_held)) {
          held += token.pct_held;
          heldKnown = true;
        }
      });
    });
    const proven = ((state.docs.funding && state.docs.funding.common_funders) || []).find((funder) => {
      return funder.same_owner_proven === true && !isExchange(funder.address, map);
    });
    const alerts = ((state.docs.alerts && state.docs.alerts.alerts) || []).slice().sort((a, b) => {
      return new Date(b.detected_at || 0) - new Date(a.detected_at || 0);
    });
    const latest = alerts[0];
    const paper = paperStats();
    const coverage = (state.docs.wallets && state.docs.wallets.coverage) || {};
    const unresolved = coverage.screenshot_addresses_unresolved || [];
    const cards = [
      {
        k: "Matched wallets",
        v: String(matched.length),
        s: `Screenshot claim: about ${CLAIM.wallets} wallets (${CLAIM.source}). ${unresolved.length ? unresolved.length + " partial addresses were not resolved." : "The full cluster is not reconstructed in this file."}`,
      },
      {
        k: "COGE held by matched wallets",
        v: heldKnown ? formatPct(held) : "—",
        s: `Added from the matched rows. Screenshot claim for the full cluster: ${CLAIM.cogePct}%. That full figure is not verified here.`,
      },
      {
        k: "Private funder found",
        v: proven ? "Yes" : "No",
        s: proven
          ? `${labelFor(proven.address, map)} is marked as the same owner.`
          : "Trails stop at exchange and busy service wallets. A shared exchange wallet is not the cabal funder.",
      },
      {
        k: "Possible next play",
        v: latest ? (latest.symbol || short(latest.mint)) : "None yet",
        s: latest
          ? `Market cap at detection ${formatUsd(latest.mcap_at_detection)}. ${formatET(latest.detected_at)}.`
          : "Flagged when a matched wallet buys a token that is not already known.",
      },
      {
        k: "Paper result",
        v: paper.decided ? formatPnl(paper.average) : "—",
        s: paper.decided
          ? `Simulated average of the latest mark. Win rate ${paper.wins} of ${paper.decided}. Not dollars and not an order.`
          : "No simulated results yet. Paper tracking starts after a possible next play.",
      },
    ];
    $("stats").innerHTML = cards.map((card) => (
      `<article class="stat"><p class="k">${esc(card.k)}</p><p class="v">${esc(card.v)}</p><p class="s">${esc(card.s)}</p></article>`
    )).join("");
    const stamp = newestStamp();
    $("file-time").textContent = stamp ? "Files as of " + formatET(stamp.stamp) + "." : "No file time yet.";
  }

  function paperStats() {
    const rows = (state.docs.paper && state.docs.paper.paper) || [];
    let wins = 0;
    let decided = 0;
    let sum = 0;
    rows.forEach((row) => {
      const latest = latestMark(row);
      if (!latest) return;
      decided += 1;
      sum += latest.pnl;
      if (latest.pnl > 0) wins += 1;
    });
    return { wins, decided, average: decided ? sum / decided : null };
  }

  function latestMark(row) {
    const order = ["6h", "1h", "15m"];
    for (let i = 0; i < order.length; i += 1) {
      const checkpoint = row.checkpoints && row.checkpoints[order[i]];
      if (checkpoint && isNum(checkpoint.pnl_pct)) return { pnl: checkpoint.pnl_pct, horizon: order[i] };
    }
    return null;
  }

  function renderWallets() {
    const filters = $("wallet-filters");
    const views = [
      ["watched", "Watched"],
      ["matched", "Screenshot matches"],
      ["holders", "Other holders"],
    ];
    filters.innerHTML = views.map(([id, label]) => (
      `<button type="button" data-view="${id}" aria-pressed="${state.walletView === id}">${label}</button>`
    )).join("");
    const list = wallets().filter((wallet) => {
      if (wallet.role === "exchange_or_service" || wallet.role === "unlabeled_busy_funder") return false;
      if (state.walletView === "matched") return isMatched(wallet);
      if (state.walletView === "holders") return !wallet.watch && !isMatched(wallet);
      return wallet.watch === true;
    });
    const host = $("wallet-list");
    if (!list.length) {
      host.innerHTML = `<p class="empty">No wallets in this view.</p>`;
      return;
    }
    host.innerHTML = list.map((wallet) => {
      const holdings = (wallet.tokens || []).map((token) => {
        const name = token.symbol || short(token.mint);
        return `${esc(name)} ${esc(formatPct(token.pct_held))}`;
      }).join(" · ") || "No token share in this file";
      const roleClass = isMatched(wallet) ? "role" : "role plain";
      const note = isMatched(wallet)
        ? "Matched the screenshot. Ownership is not independently verified."
        : (wallet.watch ? "Watched. Not confirmed as a cluster member." : "Shown as a holder only. Not a monitored cluster wallet.");
      const extra = (wallet.associated_mints || []).map((mint) => {
        const name = mint === COGE ? "COGE" : (mint === DEMOCAT ? "Democat candidate, not confirmed" : short(mint));
        return `<span>${esc(name)}</span> ${dexLink(mint)}`;
      }).join(" ");
      return `<article class="card">
        <h3>${esc(wallet.label || short(wallet.address))}</h3>
        <p class="${roleClass}">${esc(ROLE[wallet.role] || wallet.role || "Wallet")}</p>
        <p class="addr">${esc(wallet.address)}</p>
        <p>${holdings}</p>
        <p class="note">${esc(note)}</p>
        ${extra ? `<p>${extra}</p>` : ""}
        <div class="links">${accountLinks(wallet.address)}<button type="button" data-copy="${esc(wallet.address)}">Copy address</button></div>
      </article>`;
    }).join("");
  }

  function renderFunding() {
    const doc = state.docs.funding || {};
    const map = walletMap();
    const proven = (doc.common_funders || []).find((funder) => funder.same_owner_proven === true && !isExchange(funder.address, map));
    $("funder-card").innerHTML = `<article class="card">
      <h3>Private funding wallet: ${proven ? "found" : "not found"}</h3>
      <p class="note">${proven
        ? esc(labelFor(proven.address, map)) + " is marked as the same owner."
        : "No private common funder is in this file. Gate, Binance, Bybit, Kraken, SideShift, and other shared service wallets are not the cabal funder."}</p>
      ${doc.warning ? `<p class="note">${esc(doc.warning)}</p>` : ""}
    </article>`;
    const edges = doc.edges || [];
    $("funding-list").innerHTML = edges.length ? edges.map((edge) => {
      const source = edge.funder_label || labelFor(edge.funder, map);
      const exchange = isExchange(edge.funder, map) || edge.stop_reason === "busy";
      return `<article class="card">
        <h3>${esc(labelFor(edge.wallet, map))} received ${esc(formatSol(edge.amount_sol))}</h3>
        <p>From ${esc(source)}. ${formatET(edge.time)}.</p>
        <p class="note">${exchange ? "Exchange or busy service. Not the cabal funder." : "Not marked as proof of one owner."}</p>
        <div class="links">${accountLinks(edge.wallet)}${edge.tx_url ? link(edge.tx_url, "Transaction") : ""}</div>
      </article>`;
    }).join("") : `<p class="empty">No funding rows in this file.</p>`;
    drawFunding(edges, map);
  }

  function drawFunding(edges, map) {
    const host = $("funding-chart");
    if (!window.d3 || !edges.length) {
      host.innerHTML = `<p class="empty">The list above is the funding trail.</p>`;
      return;
    }
    const ids = new Set();
    edges.forEach((edge) => { ids.add(edge.funder); ids.add(edge.wallet); });
    const nodes = Array.from(ids).map((address) => ({
      id: address,
      label: labelFor(address, map),
      exchange: isExchange(address, map),
      matched: isMatched(map.get(address) || {}),
      r: isExchange(address, map) ? 16 : 22,
    }));
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const links = edges.map((edge) => ({ source: byId.get(edge.funder), target: byId.get(edge.wallet), sol: edge.amount_sol }))
      .filter((link) => link.source && link.target);
    mountGraph(host, nodes, links, "Funding graph. Exchange nodes are not the cabal funder. Details are in the list.");
  }

  function bubbleChoice() {
    const tokens = (state.docs.bubbles && state.docs.bubbles.tokens) || [];
    const early = (state.docs.early_buys && state.docs.early_buys.early_buys) || [];
    if (state.bubble === "coge") return tokens.find((token) => token.mint === COGE) || null;
    if (state.bubble === "democat") return tokens.find((token) => token.mint === DEMOCAT) || null;
    if (state.bubble === "coach") return null;
    const extras = tokens.filter((token) => token.mint !== COGE && token.mint !== DEMOCAT);
    const wanted = state.launchMint || (early[0] && early[0].mint) || (extras[0] && extras[0].mint);
    return extras.find((token) => token.mint === wanted) || null;
  }

  function renderBubbles() {
    const picks = [
      ["coge", "COGE"],
      ["democat", "Democat"],
      ["coach", "Coach"],
      ["new", "New launches"],
    ];
    $("bubble-picks").innerHTML = picks.map(([id, label]) => (
      `<button type="button" data-bubble="${id}" aria-pressed="${state.bubble === id}">${label}</button>`
    )).join("");
    const doc = state.docs.bubbles || {};
    const minutes = Math.round((doc.requested_refresh_seconds || 1800) / 60);
    $("bubble-updated").textContent = doc.updated_at
      ? `Last updated ${formatET(doc.updated_at)}. Rebuilt every ${minutes} minutes.`
      : `Rebuilt every ${minutes} minutes. No update time in this file.`;
    const token = bubbleChoice();
    let caption = "COGE mint " + COGE + ". The screenshot’s Cluster 1 was about 63 wallets and 44.65% of supply. This map is only the holders in the file.";
    if (state.bubble === "democat") caption = "Democat candidate " + DEMOCAT + " is not confirmed as the cabal’s token.";
    if (state.bubble === "coach") caption = "Coach is unresolved. No mint is confirmed, so this view stays empty.";
    if (state.bubble === "new") caption = token ? "A token matched wallets bought outside the known list." : "No new-launch holder map in this file yet.";
    $("bubble-caption").textContent = caption;
    drawBubbles(token);
    const embed = $("bubble-embed");
    const example = state.sources.bubbles === "sample" || (doc.example === true);
    const mint = token && token.mint;
    const open = [
      mint ? link(safeUrl(mint, "https://dexscreener.com/solana/"), "DexScreener") : "",
      mint ? link("https://app.bubblemaps.io/sol/token/" + mint, "Open in Bubblemaps") : "",
    ].filter(Boolean).join(" ");
    if (!mint || example || !B58.test(mint)) {
      embed.innerHTML = `<p class="note">The official Bubblemaps frame stays off this page until a live mint is selected. It is omitted for example data and for Coach until a mint is confirmed. ${open}</p>`;
      return;
    }
    const src = "https://iframe.bubblemaps.io/map?chain=solana&address=" + encodeURIComponent(mint) + "&partnerId=demo";
    embed.innerHTML = `<p class="note">Official Bubblemaps map. It loads only if you ask, so the page stays light on a phone. Their demo partner may be rate-limited. ${open}</p>
      <button type="button" id="show-bubblemaps" data-src="${esc(src)}">Show Bubblemaps map</button>`;
  }

  function drawBubbles(token) {
    const host = $("bubble-chart");
    const detail = $("bubble-detail");
    if (!token || !(token.holders || []).length) {
      host.innerHTML = `<p class="empty">No holder bubbles for this view.</p>`;
      detail.innerHTML = `<p class="empty">Nothing selected.</p>`;
      return;
    }
    const map = walletMap();
    const nodes = (token.holders || []).map((holder) => ({
      id: holder.address,
      label: labelFor(holder.address, map),
      pct: holder.pct_supply,
      matched: holder.reported_cluster_id === "coge-screenshot-1",
      exchange: false,
      r: 18,
    }));
    const byId = new Map(nodes.map((node) => [node.id, node]));
    (token.links || []).forEach((link) => {
      if (link.source && !byId.has(link.source)) {
        const node = {
          id: link.source,
          label: labelFor(link.source, map),
          pct: null,
          matched: false,
          exchange: true,
          r: 14,
        };
        nodes.push(node);
        byId.set(node.id, node);
      }
    });
    const max = Math.max(...nodes.map((node) => (isNum(node.pct) ? node.pct : 0)), 1);
    const scale = window.d3 ? d3.scaleSqrt().domain([0, max]).range([16, 42]) : null;
    nodes.forEach((node) => {
      if (!node.exchange && scale && isNum(node.pct)) node.r = scale(node.pct);
    });
    const links = (token.links || []).map((link) => ({
      source: byId.get(link.source),
      target: byId.get(link.target),
      sol: link.amount_sol,
    })).filter((link) => link.source && link.target);
    if (!window.d3) {
      host.innerHTML = `<p class="empty">Chart library did not load. Tap a wallet below.</p>`;
    } else {
      mountGraph(host, nodes, links, "Holder bubbles sized by percent of supply.", (node) => {
        state.selected = node.id;
        showBubble(node, token);
      });
    }
    const selected = nodes.find((node) => node.id === state.selected) || null;
    if (selected) showBubble(selected, token);
    else detail.innerHTML = `<p class="empty">Tap a bubble to see the address.</p>`;
  }

  function showBubble(node, token) {
    const map = walletMap();
    const wallet = map.get(node.id);
    const kind = node.exchange ? "Exchange or service. Not the cabal funder." : (node.matched ? "Matched the screenshot. Not independently verified." : "Holder. Not confirmed as a cluster member.");
    $("bubble-detail").innerHTML = `<h3>${esc(node.label)}</h3>
      <p class="${node.exchange ? "role exchange" : (node.matched ? "role" : "role plain")}">${esc(wallet ? (ROLE[wallet.role] || wallet.role) : (node.exchange ? "Exchange or service" : "Holder"))}</p>
      <p>${node.pct == null ? "No supply share. This node is a funding source." : esc(formatPct(node.pct)) + " of " + esc(token.symbol || "this token")}</p>
      <p class="note">${esc(kind)}</p>
      <p class="addr">${esc(node.id)}</p>
      <div class="links">${accountLinks(node.id)} ${dexLink(token.mint)} <button type="button" data-copy="${esc(node.id)}">Copy address</button></div>`;
  }

  function mountGraph(host, nodes, links, label, onPick) {
    if (host.__sim) {
      host.__sim.stop();
      state.sims = state.sims.filter((sim) => sim !== host.__sim);
      host.__sim = null;
    }
    const width = Math.max(host.clientWidth || 320, 280);
    const height = width < 640 ? 340 : 460;
    host.innerHTML = "";
    const svg = d3.select(host).append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img").attr("aria-label", label);
    const color = (node) => (node.exchange ? "#e3c48a" : (node.matched ? "#9ed4bc" : "#8f9a90"));
    const linkSel = svg.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", "#5c655c").attr("stroke-width", 1.2);
    const nodeSel = svg.append("g").selectAll("g").data(nodes).join("g").style("cursor", "pointer");
    nodeSel.append("circle").attr("r", (node) => node.r).attr("fill", color).attr("fill-opacity", 0.9)
      .attr("stroke", "#121612").attr("stroke-width", 2);
    nodeSel.append("text").text((node) => (node.r > 20 || node.matched || node.exchange ? node.label : ""))
      .attr("y", (node) => node.r + 12).attr("text-anchor", "middle").attr("fill", "#f4f1ea").attr("font-size", 11);
    nodeSel.on("click", (_event, node) => { if (onPick) onPick(node); });
    const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      nodes.forEach((node, index) => {
        const column = node.exchange ? width * 0.28 : width * 0.68;
        const row = 36 + (index % Math.ceil(nodes.length / 2)) * 36;
        node.x = column;
        node.y = Math.min(height - 24, row);
      });
      linkSel.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      nodeSel.attr("transform", (node) => `translate(${node.x},${node.y})`);
      return;
    }
    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).distance(70))
      .force("charge", d3.forceManyBody().strength(-80))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((node) => node.r + 10));
    sim.on("tick", () => {
      nodes.forEach((node) => {
        node.x = Math.max(node.r + 6, Math.min(width - node.r - 6, node.x));
        node.y = Math.max(node.r + 6, Math.min(height - node.r - 18, node.y));
      });
      linkSel.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      nodeSel.attr("transform", (node) => `translate(${node.x},${node.y})`);
    });
    state.sims.push(sim);
    host.__sim = sim;
    const drag = d3.drag().on("start", (event, node) => {
      if (!event.active) sim.alphaTarget(0.2).restart();
      node.fx = node.x; node.fy = node.y;
    }).on("drag", (event, node) => {
      node.fx = event.x; node.fy = event.y;
    }).on("end", (event, node) => {
      if (!event.active) sim.alphaTarget(0);
      node.fx = null; node.fy = null;
    });
    nodeSel.call(drag);
  }

  function renderTransactions() {
    const doc = state.docs.transactions || {};
    const rows = (doc.transactions || []).slice().sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
    const map = walletMap();
    const options = [{ id: "all", label: "All watched wallets" }];
    wallets().filter((wallet) => wallet.watch).forEach((wallet) => options.push({ id: wallet.address, label: wallet.label || short(wallet.address) }));
    $("tx-filter").innerHTML = `<label>Wallet <select id="tx-wallet">${options.map((option) => (
      `<option value="${esc(option.id)}"${state.txWallet === option.id ? " selected" : ""}>${esc(option.label)}</option>`
    )).join("")}</select></label>`;
    const shown = rows.filter((row) => state.txWallet === "all" || row.address === state.txWallet);
    const coverage = doc.coverage || {};
    const meta = coverage.wallets_queried
      ? `<p class="note">${coverage.wallets_queried.length} wallets queried. The API returned ${coverage.api_returned_count == null ? "—" : coverage.api_returned_count} trades in this window, from ${formatET(coverage.retention_start)}. Pump.fun and PumpSwap only.</p>`
      : "";
    if (!shown.length) {
      $("tx-list").innerHTML = meta + `<p class="empty">No trades in this file. An empty list is not proof the wallets were idle outside the window.</p>`;
      return;
    }
    $("tx-list").innerHTML = meta + shown.map((row) => {
      const side = String(row.side || "").toLowerCase();
      return `<article class="card">
        <h3>${esc(labelFor(row.address, map))}</h3>
        <p>${formatET(row.time)}</p>
        <p><span class="${side === "buy" ? "side-buy" : "side-sell"}">${esc(side || "trade")}</span> ${esc(row.symbol || short(row.mint))} · ${esc(formatSol(row.amount_sol))}</p>
        <p class="note">${row.signature ? esc(short(row.signature)) : "No signature from this source. The row is kept by wallet, slot, and mint."}</p>
        <div class="links">${dexLink(row.mint)} ${accountLinks(row.address)}</div>
      </article>`;
    }).join("");
  }

  function renderAlerts() {
    const doc = state.docs.alerts || {};
    const rows = (doc.alerts || []).slice().sort((a, b) => new Date(b.detected_at || 0) - new Date(a.detected_at || 0));
    const rule = doc.rule || {};
    const ruleText = `<p class="note">${esc(rule.trigger || "A screenshot-matched wallet buys an unknown mint.")} ${esc(rule.coach_mint_status || "Coach mint is unresolved.")}</p>`;
    if (!rows.length) {
      $("alert-list").innerHTML = ruleText + `<p class="empty">No possible next play yet.</p>${doc.warning ? `<p class="note">${esc(doc.warning)}</p>` : ""}`;
      return;
    }
    $("alert-list").innerHTML = ruleText + rows.map((alert) => {
      const age = isNum(alert.token_age_s) ? `Token age at detection: ${Math.round(alert.token_age_s / 60)} minutes.` : "Launch time was not known, so this buy is not labeled a new launch by itself.";
      return `<article class="card">
        <p class="role">Possible next cabal play</p>
        <h3>${esc(alert.symbol || "New token")}</h3>
        <p class="addr">${esc(alert.mint)}</p>
        <p>Detected ${formatET(alert.detected_at)}. Market cap then: ${esc(formatUsd(alert.mcap_at_detection))}.</p>
        <p>${esc(alert.cluster_wallet_count == null ? "—" : String(alert.cluster_wallet_count))} matched wallet${alert.cluster_wallet_count === 1 ? "" : "s"}.</p>
        <p class="note">${esc(age)}</p>
        <div class="links">${dexLink(alert.mint)}</div>
      </article>`;
    }).join("");
  }

  function renderEarly() {
    const doc = state.docs.early_buys || {};
    const minutes = Math.round((doc.requested_refresh_seconds || 1800) / 60);
    $("early-updated").textContent = doc.updated_at
      ? `Last updated ${formatET(doc.updated_at)}. Rebuilt every ${minutes} minutes.`
      : `Rebuilt every ${minutes} minutes.`;
    const rows = doc.early_buys || [];
    if (!rows.length) {
      $("early-list").innerHTML = `<p class="empty">No new launches in this file.</p>${doc.warning ? `<p class="note">${esc(doc.warning)}</p>` : ""}`;
      return;
    }
    $("early-list").innerHTML = rows.map((row) => `<article class="card">
      <h3>${esc(row.symbol || "New token")}</h3>
      <p class="addr">${esc(row.mint)}</p>
      <p>First seen buy ${formatET(row.first_buy_at)}.</p>
      <p>Market cap at detection ${esc(formatUsd(row.mcap_at_detection))}. Current market cap ${esc(formatUsd(row.current_mcap))}.</p>
      <p>${esc(row.cluster_wallet_count == null ? "—" : String(row.cluster_wallet_count))} matched wallets. Combined ${esc(formatSol(row.total_sol))}.</p>
      <p class="note">${row.early_buyer_proven ? "Marked as an early buyer from a launch record." : "Not proof this wallet was an early buyer."}</p>
      <div class="links">${dexLink(row.mint)}</div>
    </article>`).join("");
  }

  function renderPaper() {
    const doc = state.docs.paper || {};
    const rows = doc.paper || [];
    const stats = paperStats();
    const model = doc.model || {};
    $("paper-summary").innerHTML = `<article class="card">
      <p class="role">Simulated</p>
      <h3>${stats.decided ? `${stats.wins} of ${stats.decided} positive` : "No marks yet"}</h3>
      <p class="note">${esc(model.formula || "(checkpoint market cap / entry market cap - 1) × 100")}. Fees are not included. This is not executable profit.</p>
      ${doc.warning ? `<p class="note">${esc(doc.warning)}</p>` : ""}
    </article>`;
    if (!rows.length) {
      $("paper-list").innerHTML = `<p class="empty">No paper rows yet. A row is created only after a possible next play is seen live.</p>`;
      return;
    }
    const names = { "15m": "+15 min", "1h": "+1 hour", "6h": "+6 hours" };
    $("paper-list").innerHTML = rows.map((row) => {
      const checks = ["15m", "1h", "6h"].map((key) => {
        const checkpoint = (row.checkpoints || {})[key] || {};
        let value = "Not due yet";
        if (checkpoint.status === "unavailable") value = "No price";
        if (checkpoint.status === "observed") value = `${formatUsd(checkpoint.mcap)} · ${formatPnl(checkpoint.pnl_pct)}`;
        return `<div class="check"><span>${names[key]}</span><span>${esc(value)}</span></div>`;
      }).join("");
      return `<article class="card">
        <h3>${esc(row.symbol || short(row.mint))}</h3>
        <p>Entry ${formatET(row.entry_at)} at ${esc(formatUsd(row.entry_mcap))} market cap.</p>
        <div class="checks">${checks}</div>
        <div class="links">${dexLink(row.mint)}</div>
      </article>`;
    }).join("");
  }

  function render() {
    banner();
    ["summary", "wallets", "funding", "bubbles", "transactions", "alerts", "early", "paper"].forEach((name) => {
      try {
        ({
          summary: renderSummary,
          wallets: renderWallets,
          funding: renderFunding,
          bubbles: renderBubbles,
          transactions: renderTransactions,
          alerts: renderAlerts,
          early: renderEarly,
          paper: renderPaper,
        })[name]();
      } catch (err) {
        console.error(name, err);
      }
    });
    const missing = FILES.every((name) => state.sources[name] === "missing");
    $("live-status").textContent = missing ? "Data files could not be loaded." : "Data refreshed.";
    document.body.dataset.ready = missing ? "missing" : "ready";
  }

  document.addEventListener("click", (event) => {
    const view = event.target.closest("[data-view]");
    if (view) {
      state.walletView = view.getAttribute("data-view");
      renderWallets();
      return;
    }
    const bubble = event.target.closest("[data-bubble]");
    if (bubble) {
      state.bubble = bubble.getAttribute("data-bubble");
      state.selected = null;
      renderBubbles();
      return;
    }
    const copy = event.target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.getAttribute("data-copy")).catch(() => {});
      return;
    }
    const showMap = event.target.closest("#show-bubblemaps");
    if (showMap) {
      const frame = document.createElement("iframe");
      frame.title = "Bubblemaps holder map";
      frame.allow = "clipboard-write";
      frame.src = showMap.getAttribute("data-src");
      showMap.replaceWith(frame);
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.id === "tx-wallet") {
      state.txWallet = event.target.value;
      renderTransactions();
    }
  });

  async function refresh() {
    if (document.hidden) return;
    await loadAll();
    render();
  }

  $("refresh").addEventListener("click", refresh);
  refresh();
  setInterval(refresh, PAGE_MS);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
})();
