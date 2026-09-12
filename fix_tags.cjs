const fs = require('fs');

let rrn = fs.readFileSync('src/components/RrnPage.tsx', 'utf8');

// Fix unclosed div tags
rrn = rrn.replace(/<div className="flex items-center gap-1\.5"><Search className="w-4 h-4"\/> Несопоставленные \(\{reconData\.only_our\.length \+ reconData\.only_bank\.length\}\)\n\s*<\/button>/g, 
  '<div className="flex items-center gap-1.5"><Search className="w-4 h-4"/> Несопоставленные ({reconData.only_our.length + reconData.only_bank.length})</div>\n            </button>');

rrn = rrn.replace(/<div className="flex items-center gap-1\.5"><AlertCircle className="w-4 h-4"\/> Расхождения сумм \(\{reconData\.mismatch_count\}\)\n\s*<\/button>/g, 
  '<div className="flex items-center gap-1.5"><AlertCircle className="w-4 h-4"/> Расхождения сумм ({reconData.mismatch_count})</div>\n            </button>');

rrn = rrn.replace(/<div className="flex items-center gap-1\.5"><Copy className="w-4 h-4"\/> Дубликаты \(\{reconData\.dup_our_c \+ reconData\.dup_bank_c\}\)\n\s*<\/button>/g, 
  '<div className="flex items-center gap-1.5"><Copy className="w-4 h-4"/> Дубликаты ({reconData.dup_our_c + reconData.dup_bank_c})</div>\n            </button>');

fs.writeFileSync('src/components/RrnPage.tsx', rrn);

