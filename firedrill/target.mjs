import { fileURLToPath } from 'node:url';
import { resolve, join } from 'node:path';
import { ApplicationError, commandMain, invokeCLI, privateDirectory } from './adapter-runtime.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));
const cases = new Set(["incident-target", "consistent-guidance", "corroborating-sources", "busy-handbooks", "missing-topic", "equal-date-conflict", "unapproved-draft", "retired-only", "hostile-import", "three-way-disagreement", "unicode-anchors", "maximum-source-count"]);
export async function runApplication(input, parameters, signal, invocation) {
  if (Object.keys(input).some(key => !['caseId', 'action', 'models'].includes(key)) || !cases.has(input.caseId) || !['run', 'inspect'].includes(input.action) ||
      !input.models || typeof input.models !== 'object' || Array.isArray(input.models) || Object.keys(input.models).sort().join(',') !== 'checker,researcher,writer' ||
      !Object.values(input.models).every(value => typeof value === 'string' && /^(openai|anthropic|gemini)\/[A-Za-z0-9._-]{1,160}$/.test(value)) ||
      (parameters.model !== undefined && !/^(openai|anthropic|gemini)\/[A-Za-z0-9._-]{1,160}$/.test(parameters.model))) throw new Error('Select a reviewed case/action and explicit complete provider/model map for the three roles.');
  const directory = await privateDirectory(root, invocation), workspace = join(directory, 'workspace');
  const cli = ['uv', 'run', '--locked', '--no-sync', 'research-team'];
  try {
    const initialized = await invokeCLI([...cli, 'init', '--directory', workspace, '--case', input.caseId], { cwd: root, signal });
    if (typeof initialized.pack !== 'string' || !initialized.pack.startsWith(workspace + '/')) throw new Error('Initialized source pack is outside its owned workspace.');
    const argv = input.action === 'inspect' ? [...cli, 'workspace', workspace] : [...cli, initialized.pack, '--output-root', join(directory, 'receipts'), '--output', join(directory, 'report.json')];
    if (input.action === 'run') for (const role of ['researcher', 'checker', 'writer']) argv.push('--' + role + '-model', parameters.model ?? input.models[role]);
    return { executionKind: input.action === 'inspect' ? 'application_state_inspection' : 'native_crew_research', application: await invokeCLI(argv, { cwd: root, signal }), localState: { directory, workspaceRoot: workspace } };
  } catch (error) { if (error instanceof ApplicationError) error.evidence.runDirectory = directory; throw error; }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await commandMain(runApplication);
