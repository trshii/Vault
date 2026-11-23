/*
 * vault_add.js — Templater user script
 * -------------------------------------
 * Triggers the Vault backend to scan for new or modified markdown files
 * and refreshes Dashboard.md.
 */

const { spawnSync } = require("child_process");

module.exports = async function vault_add(tp) {
    // Automatically detects your vault's root folder on your hard drive.
    const VAULT_ROOT = app.vault.adapter.getBasePath();



    // ==========================================
    // USER CONFIGURATION
    // ==========================================
    
    // Default: Assumes you placed the .exe and data folder inside a ".vault" directory.
    // If you moved them, edit the strings below.
    const EXEC_PATH      = VAULT_ROOT + "/.vault/Vault.exe"; 
    const DB_PATH        = VAULT_ROOT + "/.vault/data/finance.db"; 
    
    // Default: Assumes Dashboard.md is at the root of your vault.
    const DASHBOARD_PATH = VAULT_ROOT + "/Dashboard.md"; 
    // ==========================================
    // Everything below is not recommended for changing...
    // ==========================================
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    new Notice("Scanning vault for updates...");
    
    if (app.workspace.activeLeaf && app.workspace.activeLeaf.view && app.workspace.activeLeaf.view.save) {
        await app.workspace.activeLeaf.view.save();
    }

    await new Promise(resolve => setTimeout(resolve, 200));

    const result = spawnSync(
        EXEC_PATH,
        ["--db", DB_PATH, "--dashboard", DASHBOARD_PATH],
        { encoding: "utf-8" }
    );

    
    if (result.error) {
        new Notice(`Failed to run vault_cli.py: ${result.error.message}`);
        console.error(result.error);
        return;
    }

    console.log(result.stdout);
    if (result.stderr) {
        console.warn(result.stderr);
    }

    if (result.status === 0) {
        new Notice("Vault scan complete — Dashboard updated.");
    } else if (result.status === 1) {
        new Notice("Vault scan finished, but some lines had errors — check console.");
    } else {
        new Notice("vault_cli.py failed — check console.");
    }

    return "";
};