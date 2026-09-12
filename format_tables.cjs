const fs = require('fs');

function formatTables(file) {
    let content = fs.readFileSync(file, 'utf8');
    // For RrnPage
    content = content.replace(/className="([^"]*?text-right[^"]*?)"\>\{fmt/g, 'className="$1 tabular-nums tracking-tight whitespace-nowrap">{fmt');
    fs.writeFileSync(file, content);
}

formatTables('src/components/RrnPage.tsx');
formatTables('src/components/AnalyticsPage.tsx');
