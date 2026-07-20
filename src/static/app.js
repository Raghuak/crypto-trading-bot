// --- Dashboard Controller Logic ---

document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const elBotModeBadge = document.getElementById("bot-mode-badge");
    const elBotModeText = document.getElementById("bot-mode-text");
    const elBotRunningBadge = document.getElementById("bot-running-badge");
    const elRunningDot = document.getElementById("running-dot");
    const elBotRunningText = document.getElementById("bot-running-text");
    
    const elBtnToggleTrading = document.getElementById("btn-toggle-trading");
    const elToggleText = document.getElementById("toggle-text");
    const elBtnCloseAll = document.getElementById("btn-close-all");
    
    const elTotalEquity = document.getElementById("val-total-equity");
    const elAvailableBalance = document.getElementById("val-available-balance");
    const elNetPnl = document.getElementById("val-net-pnl");
    const elNetPnlPct = document.getElementById("val-net-pnl-pct");
    const elCardNetPnl = document.getElementById("card-net-pnl");
    const elWinRate = document.getElementById("val-win-rate");
    const elWinRateText = document.getElementById("val-win-rate-text");
    const elProfitFactor = document.getElementById("val-profit-factor");
    
    const elPositionsBody = document.getElementById("positions-body");
    const elOpenPositionsCountBadge = document.getElementById("open-positions-count-badge");
    const elHistoryBody = document.getElementById("history-body");
    
    const elConnStatus = document.getElementById("conn-status");
    const elConsoleLogContainer = document.getElementById("console-log-container");
    
    let ws = null;
    let reconnectInterval = null;

    // --- Action Button Handlers ---
    
    // Toggle Pause/Resume bot trading execution loop
    elBtnToggleTrading.addEventListener("click", async () => {
        try {
            elBtnToggleTrading.disabled = true;
            const res = await fetch("/api/actions/toggle_trading", { method: "POST" });
            const data = await res.json();
            
            if (data.status === "success") {
                updateTradingActiveUI(data.trading_active);
            }
        } catch (err) {
            console.error("Error toggling bot execution state:", err);
            alert("Failed to communicate with webserver action endpoint.");
        } finally {
            elBtnToggleTrading.disabled = false;
        }
    });

    // Close all open positions manually
    elBtnCloseAll.addEventListener("click", async () => {
        const confirmed = confirm("⚠️ WARNING: Are you sure you want to FORCE-CLOSE all active open positions at market price? This will instantly execute sell orders on the exchange.");
        if (!confirmed) return;
        
        try {
            elBtnCloseAll.disabled = true;
            elBtnCloseAll.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Exiting...';
            
            const res = await fetch("/api/actions/close_all", { method: "POST" });
            const data = await res.json();
            
            alert(data.message);
            // Refresh dashboard data instantly
            fetchRestFallback();
        } catch (err) {
            console.error("Error executing emergency exit:", err);
            alert("Emergency exit execution failed.");
        } finally {
            elBtnCloseAll.disabled = false;
            elBtnCloseAll.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> Force Close All';
        }
    });

    // --- State Update Helpers ---

    function updateTradingActiveUI(isActive) {
        if (isActive) {
            // Running State
            elRunningDot.className = "status-dot green-glow";
            elBotRunningText.textContent = "RUNNING";
            elBtnToggleTrading.className = "action-btn";
            elBtnToggleTrading.innerHTML = '<i class="fa-solid fa-pause"></i> <span id="toggle-text">Pause Bot</span>';
        } else {
            // Paused State
            elRunningDot.className = "status-dot yellow-glow";
            elBotRunningText.textContent = "PAUSED VIA UI";
            elBtnToggleTrading.className = "action-btn active-pause";
            elBtnToggleTrading.innerHTML = '<i class="fa-solid fa-play"></i> <span id="toggle-text">Resume Bot</span>';
        }
    }

    function updateMetrics(data) {
        // Mode & Status
        updateTradingActiveUI(data.trading_active);
        
        if (data.paper_trading) {
            elBotModeBadge.className = "status-badge green-glow";
            elBotModeText.textContent = "PAPER TRADING";
            elBotModeText.className = "green-text";
        } else {
            elBotModeBadge.className = "status-badge red-glow";
            elBotModeText.textContent = "LIVE TRADING";
            elBotModeText.className = "red-text";
        }

        // Equity Cards
        elTotalEquity.innerHTML = `${data.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} <span class="currency">USDT</span>`;
        elAvailableBalance.innerHTML = `${data.available_balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} <span class="currency">USDT</span>`;
        
        // PnL formatting
        const pnl = data.metrics.total_net_pnl;
        const returnPct = (pnl / (data.total_equity - pnl)) * 100 || 0;
        
        if (pnl >= 0) {
            elNetPnl.className = "card-value font-mono green-text";
            elNetPnl.innerHTML = `+${pnl.toFixed(2)} <span class="currency">USDT</span>`;
            elNetPnlPct.className = "card-footer green-text";
            elNetPnlPct.innerHTML = `<i class="fa-solid fa-caret-up"></i> +${returnPct.toFixed(2)}% Return`;
            elCardNetPnl.className = "metric-card pnl-card";
        } else {
            elNetPnl.className = "card-value font-mono red-text";
            elNetPnl.innerHTML = `${pnl.toFixed(2)} <span class="currency">USDT</span>`;
            elNetPnlPct.className = "card-footer red-text";
            elNetPnlPct.innerHTML = `<i class="fa-solid fa-caret-down"></i> ${returnPct.toFixed(2)}% Return`;
            elCardNetPnl.className = "metric-card pnl-card negative";
        }

        // Stats Cards
        elWinRate.textContent = `${data.metrics.win_rate.toFixed(1)}%`;
        elWinRateText.textContent = `${data.metrics.total_trades} total closed trades`;
        elProfitFactor.textContent = data.metrics.profit_factor;
    }

    function formatTime(isoStr) {
        if (!isoStr) return "-";
        try {
            const parts = isoStr.split("T");
            if (parts.length < 2) return isoStr.substring(0, 16);
            const datePart = parts[0];
            const timePart = parts[1];
            const mm_dd = datePart.substring(5);
            const hh_mm = timePart.substring(0, 5);
            return `${mm_dd} ${hh_mm}`;
        } catch (e) {
            return isoStr.substring(0, 16);
        }
    }

    function updatePositionsTable(positions) {
        elOpenPositionsCountBadge.textContent = `${positions.length} Active`;
        
        if (positions.length === 0) {
            elPositionsBody.innerHTML = `<tr><td colspan="9" class="empty-row">No active positions. Scanning markets...</td></tr>`;
            return;
        }

        let html = "";
        positions.forEach(pos => {
            const sideClass = pos.side.toLowerCase() === "long" || pos.side.toLowerCase() === "buy" ? "green-text" : "red-text";
            const pnlClass = pos.unrealized_pnl >= 0 ? "green-text" : "red-text";
            const sign = pos.unrealized_pnl >= 0 ? "+" : "";
            
            html += `
                <tr>
                    <td class="font-mono"><strong>${pos.symbol}</strong></td>
                    <td><span class="badge ${sideClass}">${pos.side.toUpperCase()}</span></td>
                    <td class="font-mono">${pos.entry_price.toFixed(4)}</td>
                    <td class="font-mono">${pos.last_price.toFixed(4)}</td>
                    <td class="font-mono">${pos.qty.toFixed(6)}</td>
                    <td class="font-mono ${pnlClass}"><strong>${sign}${pos.unrealized_pnl.toFixed(2)} (${sign}${pos.unrealized_pnl_pct.toFixed(2)}%)</strong></td>
                    <td class="font-mono red-text">${pos.stop_loss.toFixed(4)}</td>
                    <td class="font-mono green-text">${pos.take_profit.toFixed(4)}</td>
                    <td class="font-mono dim-text">${formatTime(pos.entry_time)}</td>
                </tr>
            `;
        });
        elPositionsBody.innerHTML = html;
    }

    function updateHistoryTable(trades) {
        const closedTrades = trades.filter(t => t.status === "CLOSED");
        
        if (closedTrades.length === 0) {
            elHistoryBody.innerHTML = `<tr><td colspan="8" class="empty-row">No closed trades recorded yet.</td></tr>`;
            return;
        }

        let html = "";
        // Show last 5 closed trades
        closedTrades.slice(0, 5).forEach(trade => {
            const pnl = trade.pnl || 0;
            const pnlPct = trade.pnl_pct || 0;
            const pnlClass = pnl >= 0 ? "green-text" : "red-text";
            const sign = pnl >= 0 ? "+" : "";
            
            html += `
                <tr>
                    <td class="font-mono"><strong>${trade.symbol}</strong></td>
                    <td class="font-mono">${trade.entry_price.toFixed(4)}</td>
                    <td class="font-mono">${trade.exit_price ? trade.exit_price.toFixed(4) : "-"}</td>
                    <td class="font-mono">${trade.entry_qty.toFixed(4)}</td>
                    <td class="font-mono ${pnlClass}">${sign}${pnlPct.toFixed(2)}%</td>
                    <td class="font-mono ${pnlClass}"><strong>${sign}${pnl.toFixed(2)}</strong></td>
                    <td><span class="dim-text">${trade.exit_order_id || 'MARKET'}</span></td>
                    <td class="font-mono dim-text">${formatTime(trade.exit_time)}</td>
                </tr>
            `;
        });
        elHistoryBody.innerHTML = html;
    }

    function updateConsoleLogs(logs) {
        if (!elConsoleLogContainer) return;
        if (!logs || logs.length === 0) {
            elConsoleLogContainer.innerHTML = `<div class="log-line system-msg">No logs available. Ready.</div>`;
            return;
        }

        let html = "";
        logs.forEach(line => {
            let logTypeClass = "log-debug";
            if (line.includes(" - ERROR - ")) {
                logTypeClass = "log-error";
            } else if (line.includes(" - WARNING - ")) {
                logTypeClass = "log-warning";
            } else if (line.includes(" - INFO - ")) {
                logTypeClass = "log-info";
            } else if (line.includes(" - CRITICAL - ")) {
                logTypeClass = "log-error";
            }
            
            let cleanedLine = line
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
                
            html += `<div class="log-line ${logTypeClass}">${cleanedLine}</div>`;
        });
        
        elConsoleLogContainer.innerHTML = html;
        elConsoleLogContainer.scrollTop = elConsoleLogContainer.scrollHeight;
    }

    // --- WebSocket Stream Core ---

    function initWebSocket() {
        if (ws) {
            ws.close();
        }

        const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${wsProto}//${window.location.host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket connection established.");
            elConnStatus.textContent = "Connected";
            elConnStatus.className = "connected";
            clearInterval(reconnectInterval);
            // Fetch initial status via REST first to populate UI instantly
            fetchRestFallback();
        };

        ws.onclose = () => {
            console.warn("WebSocket connection closed. Reconnecting...");
            elConnStatus.textContent = "Disconnected (Reconnecting...)";
            elConnStatus.className = "disconnected";
            triggerReconnect();
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
            ws.close();
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                updateMetrics(data);
                updatePositionsTable(data.open_positions);
                updateHistoryTable(data.recent_closed_trades);
                if (data.recent_logs) {
                    updateConsoleLogs(data.recent_logs);
                }
            } catch (err) {
                console.error("Error parsing WebSocket JSON payload:", err);
            }
        };
    }

    function triggerReconnect() {
        clearInterval(reconnectInterval);
        reconnectInterval = setInterval(() => {
            console.log("Attempting WebSocket reconnect...");
            initWebSocket();
        }, 5000);
    }

    // --- REST Fallback Polling (Resilience Layer) ---

    async function fetchRestFallback() {
        try {
            // 1. Fetch status details
            const resStatus = await fetch("/api/status");
            const dataStatus = await resStatus.json();
            updateMetrics(dataStatus);
            if (dataStatus.recent_logs) {
                updateConsoleLogs(dataStatus.recent_logs);
            }

            // 2. Fetch positions
            const resPositions = await fetch("/api/positions");
            const positions = await resPositions.json();
            updatePositionsTable(positions);

            // 3. Fetch trade logs
            const resTrades = await fetch("/api/trades");
            const trades = await resTrades.json();
            updateHistoryTable(trades);
        } catch (err) {
            console.error("REST fallback fetch error:", err);
        }
    }

    // Initialize
    initWebSocket();
    
    // Set fallback interval to run every 15 seconds in case WebSocket drops
    setInterval(fetchRestFallback, 15000);
});
