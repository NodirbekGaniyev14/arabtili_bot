// webapp/src/pages/v2/<modul>.ts ni node'da ishga tushiradi (tests/test_answer_check.py, tests/test_exercise_logic.py uchun).
// Modul: birinchi argument (standart — answerCheck.ts).
// stdin: [[funksiya, ...argumentlar], ...] → stdout: natijalar JSON massivi.
const path = require("path");
const fs = require("fs");

const root = path.resolve(__dirname, "..", "..");
const esbuild = require(path.join(root, "webapp", "node_modules", "esbuild"));
const built = esbuild.buildSync({
  entryPoints: [path.join(root, "webapp", "src", "pages", "v2", process.argv[2] || "answerCheck.ts")],
  bundle: true,
  format: "cjs",
  platform: "node",
  write: false,
  logLevel: "warning",
});
const mod = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(mod, mod.exports, require);

const cases = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(([fn, ...args]) => mod.exports[fn](...args))));
