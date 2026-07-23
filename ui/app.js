document.addEventListener("DOMContentLoaded", () => {
    const btnGenerate = document.getElementById("btn-generate");
    const loader = document.getElementById("loader");
    const resultsArea = document.getElementById("results-area");
    const accaBody = document.getElementById("acca-body");
    const statEdge = document.getElementById("stat-edge");
    const statLegs = document.getElementById("stat-legs");

    const navLinks = {
        "nav-dashboard": document.getElementById("view-dashboard"),
        "nav-generate": document.getElementById("view-generate"),
        "nav-fixtures": document.getElementById("view-fixtures"),
        "nav-athenizer": document.getElementById("view-athenizer"),
        "nav-settings": document.getElementById("view-settings")
    };

    const switchView = (activeNavId) => {
        Object.values(navLinks).forEach(v => v.classList.remove("active"));
        Object.keys(navLinks).forEach(k => document.getElementById(k).classList.remove("active"));
        
        document.getElementById(activeNavId).classList.add("active");
        navLinks[activeNavId].classList.add("active");
    };

    Object.keys(navLinks).forEach(id => {
        document.getElementById(id).addEventListener("click", (e) => {
            e.preventDefault();
            switchView(id);
        });
    });

    // Check backend status
    fetch("http://127.0.0.1:8500/api/status")
        .then(res => res.json())
        .then(data => console.log("Backend Status:", data))
        .catch(err => console.error("Backend not running:", err));

    // Dynamic Leagues Loader
    const MAJOR_LEAGUES = ["Premier League", "LaLiga", "Bundesliga", "Ligue 1", "Champions League", "Europa League", "Europa Conference League"];

    const loadLeagues = async (days) => {
        const container = document.getElementById("league-checkboxes");
        container.innerHTML = `<span style="color: var(--text-muted); font-size: 0.8rem; padding: 1rem;">Loading leagues for next ${days} days...</span>`;
        try {
            const res = await fetch(`http://127.0.0.1:8500/api/leagues?days=${days}`);
            const data = await res.json();
            if (data.leagues && data.leagues.length > 0) {
                // Show ALL available leagues, but do not check any by default.
                // The backend will handle priority leagues if none are selected.
                container.innerHTML = data.leagues.map(l => {
                    return `<label class="league-checkbox" style="display: inline-block; margin-right: 1rem; margin-bottom: 0.5rem;"><input type="checkbox" value="${l}"> ${l}</label>`;
                }).join("");
            } else {
                container.innerHTML = `<span style="color: var(--text-muted); font-size: 0.8rem; padding: 1rem;">No leagues found.</span>`;
            }
        } catch (e) {
            container.innerHTML = `<span style="color: #ff4444; font-size: 0.8rem; padding: 1rem;">Error loading leagues.</span>`;
        }
    };

    document.getElementById("input-days").addEventListener("change", (e) => {
        loadLeagues(e.target.value);
    });

    let currentAccaData = null;

    // Export Acca Logic
    const btnExportCode = document.getElementById("btn-export-code");
    if (btnExportCode) {
        btnExportCode.addEventListener("click", async () => {
            const bookie = document.getElementById("input-export-bookie").value;
            const resBox = document.getElementById("export-results");
            
            if (!currentAccaData || !currentAccaData.legs) {
                resBox.innerHTML = `<span style="color: #ff4444;">No accumulator generated yet.</span>`;
                return;
            }
            
            btnExportCode.textContent = "Generating...";
            resBox.innerHTML = `<span style="color: var(--text-muted);">Contacting ${bookie} servers...</span>`;
            
            try {
                const response = await fetch("http://127.0.0.1:8500/api/export_code", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bookmaker: bookie, acca_data: currentAccaData })
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || "Export failed");
                }
                
                const data = await response.json();
                const bookieName = document.getElementById("input-export-bookie").options[document.getElementById("input-export-bookie").selectedIndex].text;
                const isUrl = data.code.startsWith("http://") || data.code.startsWith("https://");
                
                resBox.innerHTML = `
                    <div style="padding: 1.25rem; background: rgba(0, 200, 81, 0.08); border: 1.5px solid var(--success); border-radius: 8px; text-align: center; margin-top: 1rem; box-shadow: 0 4px 15px rgba(0, 200, 81, 0.15);">
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 1px;">Generated ${bookieName} ${isUrl ? 'Bet Slip Link' : 'Booking Code'}</div>
                        
                        <div style="display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin: 0.75rem 0;">
                            <input id="generated-code-input" type="text" readonly value="${data.code}" style="width: 100%; max-width: 480px; padding: 0.6rem 1rem; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 1.1rem; font-weight: bold; color: #00e676; background: rgba(0,0,0,0.5); border: 1px solid var(--success); border-radius: 6px; text-align: center; user-select: all; outline: none;" />
                        </div>
                        
                        <div style="display: flex; justify-content: center; gap: 0.75rem; margin-top: 0.75rem;">
                            <button id="btn-copy-code" style="padding: 0.5rem 1.25rem; font-weight: bold; background: var(--success); color: #000; border: none; border-radius: 5px; cursor: pointer; transition: all 0.2s ease;">
                                📋 Copy ${isUrl ? 'Link' : 'Code'}
                            </button>
                            ${isUrl ? `<a href="${data.code}" target="_blank" style="padding: 0.5rem 1.25rem; font-weight: bold; background: rgba(255,255,255,0.1); color: #fff; text-decoration: none; border: 1px solid rgba(255,255,255,0.2); border-radius: 5px; cursor: pointer;">🌐 Open in ${bookieName}</a>` : ''}
                        </div>
                    </div>
                `;

                const btnCopy = document.getElementById("btn-copy-code");
                if (btnCopy) {
                    btnCopy.addEventListener("click", () => {
                        const copyInput = document.getElementById("generated-code-input");
                        copyInput.select();
                        copyInput.setSelectionRange(0, 99999);
                        navigator.clipboard.writeText(data.code).then(() => {
                            btnCopy.textContent = "✓ Copied!";
                            btnCopy.style.background = "#ffffff";
                            btnCopy.style.color = "#000000";
                            setTimeout(() => {
                                btnCopy.textContent = `📋 Copy ${isUrl ? 'Link' : 'Code'}`;
                                btnCopy.style.background = "var(--success)";
                                btnCopy.style.color = "#000000";
                            }, 2000);
                        }).catch(() => {
                            // Fallback
                            document.execCommand("copy");
                            btnCopy.textContent = "✓ Copied!";
                            setTimeout(() => { btnCopy.textContent = `📋 Copy ${isUrl ? 'Link' : 'Code'}`; }, 2000);
                        });
                    });
                }
            } catch (error) {
                resBox.innerHTML = `<span style="color: #ff4444;">Error: ${error.message}</span>`;
            } finally {
                btnExportCode.textContent = "Get Code";
            }
        });
    }

    // Initial load
    loadLeagues(document.getElementById("input-days").value);

    // --- FIXTURES LOGIC (FOTMOB STYLE) ---
    let globalFixtures = [];

    const renderDateSelector = () => {
        const selector = document.getElementById("fixture-date-selector");
        let html = "";
        const today = new Date();
        for (let i = 0; i < 7; i++) {
            let d = new Date(today);
            d.setDate(today.getDate() + i);
            let label = i === 0 ? "Today" : i === 1 ? "Tomorrow" : d.toLocaleDateString('en-US', {weekday: 'short', month: 'short', day: 'numeric'});
            let dateStr = d.toISOString().split('T')[0];
            html += `<button class="date-btn ${i === 0 ? 'active' : ''}" data-date="${dateStr}">${label}</button>`;
        }
        selector.innerHTML = html;

        document.querySelectorAll(".date-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                document.querySelectorAll(".date-btn").forEach(b => b.classList.remove("active"));
                e.target.classList.add("active");
                renderFixturesForDate(e.target.dataset.date);
            });
        });
    };

    const renderFixturesForDate = (targetDateStr) => {
        const container = document.getElementById("fixtures-container");
        
        // Filter matches for this date
        const matchesForDate = globalFixtures.filter(f => {
            // f.match_date is something like "2023-10-25T14:00:00Z"
            if (!f.match_date) return false;
            return f.match_date.startsWith(targetDateStr);
        });

        if (matchesForDate.length === 0) {
            container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No fixtures scheduled for this date.</div>`;
            return;
        }

        // Group by league
        const grouped = {};
        matchesForDate.forEach(f => {
            if (!grouped[f.league]) grouped[f.league] = [];
            grouped[f.league].push(f);
        });

        let html = "";
        for (const [league, matches] of Object.entries(grouped)) {
            html += `<div class="league-group">
                        <h3><span style="font-size: 0.9em; filter: grayscale(1);">🌐</span> ${league}</h3>`;
            
            matches.forEach(m => {
                const timeStr = m.status_string || new Date(m.match_date).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                const homeLogo = `https://images.fotmob.com/image_resources/logo/teamlogo/${m.home_id}.png`;
                const awayLogo = `https://images.fotmob.com/image_resources/logo/teamlogo/${m.away_id}.png`;
                
                let scoreText = "";
                if (m.home_score !== undefined && m.home_score !== null && m.home_score !== "") {
                    scoreText = `<span class="team-score" style="margin: 0 0.5rem;">${m.home_score} - ${m.away_score}</span>`;
                }

                html += `
                    <div class="match-card">
                        <div class="match-time">${timeStr}</div>
                        <div class="match-teams">
                            <div class="team-row">
                                <img src="${homeLogo}" class="team-logo-placeholder" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\'></svg>'">
                                <span class="team-name">${m.home_team}</span>
                            </div>
                            <div class="team-row">
                                <img src="${awayLogo}" class="team-logo-placeholder" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\'></svg>'">
                                <span class="team-name">${m.away_team}</span>
                            </div>
                        </div>
                        ${scoreText}
                    </div>
                `;
            });
            html += `</div>`;
        }
        container.innerHTML = html;
    };

    const loadAllFixtures = async () => {
        const container = document.getElementById("fixtures-container");
        container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading live schedule... <div class="spinner" style="margin: 10px auto; width: 24px; height: 24px;"></div></div>`;
        try {
            // Fetch 7 days of fixtures at once
            const res = await fetch(`http://127.0.0.1:8500/api/fixtures?days=7`);
            const data = await res.json();
            if (data.fixtures) {
                globalFixtures = data.fixtures;
                // Render today's fixtures by default
                const todayStr = new Date().toISOString().split('T')[0];
                renderFixturesForDate(todayStr);
            }
        } catch(e) {
            container.innerHTML = `<div style="text-align: center; padding: 2rem; color: #ff4444;">Error loading schedule.</div>`;
        }
    };

    // Initialize Fixtures view when clicking the nav
    document.getElementById("nav-fixtures").addEventListener("click", () => {
        renderDateSelector();
        loadAllFixtures();
    });

    // Make Fixtures the Default Tab
    switchView("nav-fixtures");
    renderDateSelector();
    loadAllFixtures();


    // --- ATHENIZER LOGIC ---
    
    // Tab Switching
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".athenizer-tab-content").forEach(c => c.classList.remove("active"));
            
            e.target.classList.add("active");
            document.getElementById(e.target.dataset.target).classList.add("active");
        });
    });

    const runVet = async () => {
        const code = document.getElementById("input-vet-code").value;
        const bookie = document.getElementById("input-vet-bookie").value;
        const results = document.getElementById("vet-results");
        
        if (!code) return alert("Please enter a booking code.");

        results.classList.remove("hidden");
        results.innerHTML = `<p style="color: var(--text-muted);">Vetting ${bookie} slip: <strong>${code}</strong>...</p>
                             <div class="spinner" style="width: 20px; height: 20px; margin-top: 10px;"></div>`;
        
        try {
            const res = await fetch(`http://127.0.0.1:8500/api/athenizer/vet`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bookmaker: bookie, booking_code: code })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to process booking code.");

            let html = `<p style="color: var(--accent); font-weight: bold; margin-bottom: 1rem;">ATHENA Approval: ${data.athena_approval}</p>`;
            html += `<table style="width:100%; text-align: left; background: rgba(0,0,0,0.2); border-radius: 8px;">
                        <thead><tr style="border-bottom: 1px solid var(--glass-border);">
                            <th style="padding: 0.5rem;">Fixture</th>
                            <th style="padding: 0.5rem;">Pick</th>
                            <th style="padding: 0.5rem;">Verdict</th>
                        </tr></thead><tbody>`;
            
            data.legs.forEach(leg => {
                html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <td style="padding: 0.5rem; font-size: 0.85rem;">${leg.fixture}</td>
                            <td style="padding: 0.5rem; font-size: 0.85rem;">${leg.market}: ${leg.selection}</td>
                            <td style="padding: 0.5rem; font-size: 0.85rem; color: var(--accent);">${leg.athena_verdict}</td>
                         </tr>`;
            });
            html += `</tbody></table>`;
            results.innerHTML = html;

        } catch (e) {
            results.innerHTML = `<p style="color: #ff4444;">Error: ${e.message}</p>`;
        }
    };

    const runSplit = async () => {
        const code = document.getElementById("input-split-code").value;
        const bookie = document.getElementById("input-split-bookie").value;
        const parts = document.getElementById("input-split-parts").value;
        const results = document.getElementById("split-results");
        
        if (!code) return alert("Please enter a booking code.");

        results.classList.remove("hidden");
        results.innerHTML = `<p style="color: var(--text-muted);">Splitting slip...</p><div class="spinner" style="width: 20px; height: 20px;"></div>`;
        
        try {
            const res = await fetch(`http://127.0.0.1:8500/api/athenizer/split`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bookmaker: bookie, booking_code: code, split_count: parseInt(parts) })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to split.");

            let html = `<p style="color: var(--accent); font-weight: bold; margin-bottom: 1rem;">Successfully split into ${data.splits.length} parts.</p>`;
            data.splits.forEach((split, index) => {
                html += `<div style="background: rgba(0,0,0,0.2); padding: 1rem; border-radius: 8px; margin-bottom: 1rem; border: 1px solid var(--glass-border);">`;
                html += `<h4 style="margin-top: 0; color: var(--text-main);">Ticket ${index + 1}</h4>`;
                split.forEach(leg => {
                    html += `<div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.25rem;">• ${leg.fixture} (${leg.selection})</div>`;
                });
                html += `</div>`;
            });
            results.innerHTML = html;

        } catch (e) {
            results.innerHTML = `<p style="color: #ff4444;">Error: ${e.message}</p>`;
        }
    };

    document.getElementById("btn-vet-slip").addEventListener("click", runVet);
    document.getElementById("btn-split-slip").addEventListener("click", runSplit);
    
    // Merge placeholder
    document.getElementById("btn-merge-slips").addEventListener("click", () => {
        const results = document.getElementById("merge-results");
        results.classList.remove("hidden");
        results.innerHTML = `<p style="color: #ff4444;">Merge capability is under construction.</p>`;
    });

    // Generate Acca Logic
    btnGenerate.addEventListener("click", async () => {
        const days = parseInt(document.getElementById("input-days").value);
        const folds = parseInt(document.getElementById("input-folds").value);
        const strict = document.getElementById("input-strict").checked;
        
        // Gather selected leagues
        const checkedLeagues = Array.from(document.querySelectorAll('.league-checkbox input:checked'))
                                    .map(cb => cb.value);
        const league = checkedLeagues.length > 0 ? checkedLeagues.join(",") : null;

        // Show Loader
        loader.classList.remove("hidden");
        resultsArea.classList.add("hidden");
        accaBody.innerHTML = "";

        try {
            const response = await fetch("http://127.0.0.1:8500/api/generate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ days, folds, strict, league })
            });

            if (!response.ok) {
                const errData = await response.json();
                let errMsg = errData.detail || "Generation failed";
                if (typeof errMsg === 'object') errMsg = JSON.stringify(errMsg);
                throw new Error(errMsg);
            }

            const data = await response.json();
            currentAccaData = data;
            
            // Populate Results
            statEdge.innerText = data.total_edge ? data.total_edge.toFixed(2) + "x" : "N/A";
            statLegs.innerText = data.legs ? data.legs.length : "0";

            if (data.legs && data.legs.length > 0) {
                data.legs.forEach(leg => {
                    const tr = document.createElement("tr");
                    
                    const tdMatchDate = document.createElement("td");
                    tdMatchDate.innerText = leg.match_date || "Today";

                    const tdLeague = document.createElement("td");
                    tdLeague.innerText = leg.league || "Global";

                    const tdFixture = document.createElement("td");
                    tdFixture.innerText = leg.fixture;
                    
                    const tdSelection = document.createElement("td");
                    tdSelection.innerText = leg.market + ": " + leg.selection;
                    tdSelection.style.color = "var(--accent)";
                    tdSelection.style.fontWeight = "bold";

                    const tdEdge = document.createElement("td");
                    tdEdge.innerText = leg.edge ? leg.edge.toFixed(2) + "x" : "-";

                    tr.appendChild(tdMatchDate);
                    tr.appendChild(tdLeague);
                    tr.appendChild(tdFixture);
                    tr.appendChild(tdSelection);
                    tr.appendChild(tdEdge);
                    accaBody.appendChild(tr);
                });
                
                document.getElementById("acca-generate-code-container").classList.remove("hidden");
            } else {
                const tr = document.createElement("tr");
                const td = document.createElement("td");
                td.colSpan = 5;
                td.innerText = "No eligible fixtures found matching criteria.";
                td.style.textAlign = "center";
                tr.appendChild(td);
                accaBody.appendChild(tr);
            }

            resultsArea.classList.remove("hidden");
        } catch (error) {
            alert("Error: " + error.message);
        } finally {
            loader.classList.add("hidden");
        }
    });
});
