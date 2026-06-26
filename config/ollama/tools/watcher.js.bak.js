import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { fileURLToPath } from 'url';
import chokidar from 'chokidar';
import { gguf } from '@huggingface/gguf';
import { convertGGUFTemplateToOllama } from '@huggingface/ollama-utils';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Constants for directories inside the container
const ollamaBaseDir = '/root/.ollama';
const manifestsDir = path.join(ollamaBaseDir, 'models', 'manifests');

const processedManifests = new Set();

// Entry point
const manualModelArg = process.argv[2];

if (manualModelArg) {
  runManualPatch(manualModelArg);
} else {
  startWatcher();
}

// Manual mode: patch a specific pulled model directly
async function runManualPatch(modelArg) {
  console.log(`[INFO] Manual patch requested for model: ${modelArg}`);
  
  if (!modelArg.startsWith('hf.co/')) {
    console.error(`[ERROR] Only Hugging Face models (starting with 'hf.co/') are supported.`);
    process.exit(1);
  }

  // Format path: e.g. hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:IQ4_XS -> hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF/IQ4_XS
  let relPath = modelArg.replace(':', '/');
  if (!modelArg.includes(':')) {
    relPath += '/latest';
  }

  const filePath = path.join(manifestsDir, relPath);
  if (!fs.existsSync(filePath)) {
    console.error(`[ERROR] Manifest file not found at: ${filePath}`);
    console.error(`Please make sure you have pulled/installed the model first (e.g. ollama pull ${modelArg}).`);
    process.exit(1);
  }

  const modelNameNormalized = modelArg.includes(':') ? modelArg.split(':')[0] : modelArg;

  try {
    await processManifest(filePath, relPath, modelNameNormalized, true);
  } catch (err) {
    console.error(`[ERROR] Manual patch failed:`, err.message);
    process.exit(1);
  }
}

// Background mode: watch for new manifests as they are created
function startWatcher() {
  console.log(`Jinja Support is ready for new models...`);

  if (!fs.existsSync(manifestsDir)) {
    fs.mkdirSync(manifestsDir, { recursive: true });
  }

  const watcher = chokidar.watch(manifestsDir, {
    ignored: /(^|[\/\\])\../,
    persistent: true,
    ignoreInitial: true,
    depth: 9
  });

  watcher.on('add', async (filePath) => {
    const relPath = path.relative(manifestsDir, filePath);
    
    if (!relPath.startsWith('hf.co/')) {
      return;
    }

    if (processedManifests.has(relPath)) {
      return;
    }

    console.log(`Checking model for template patches: ${relPath}`);
    processedManifests.add(relPath);

    const modelNameNormalized = relPath.endsWith('/latest')
      ? relPath.substring(0, relPath.length - 7)
      : relPath.replace(/\/[^\/]+$/, '');

    try {
      // Wait until the model is registered and unlocked by Ollama
      await waitForModelReady(modelNameNormalized);
      await processManifest(filePath, relPath, modelNameNormalized, false);
    } catch (err) {
      console.error(`Error patching model ${modelNameNormalized}:`, err.message);
    } finally {
      // Keep in list briefly to prevent infinite loops from create trigger
      setTimeout(() => processedManifests.delete(relPath), 15000);
    }
  });
}

async function waitForModelReady(modelName, maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await fetch('http://127.0.0.1:11434/api/tags');
      const data = await res.json();

      const exists = data.models?.some(model => model.name === modelName || model.name === `${modelName}:latest`);
      if (exists) {
        console.log(`[INFO] Model '${modelName}' is fully registered in Ollama API.`);
        // Brief delay for final write lock releases
        await new Promise(resolve => setTimeout(resolve, 2000));
        return true;
      }
    } catch (err) {
      // API port might not be ready yet
    }

    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  throw new Error(`[ERROR] Timeout waiting for model '${modelName}' to become ready.`);
}

async function processManifest(manifestPath, relPath, modelNameNormalized, isManual = false) {
  const manifestContent = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  
  const modelLayer = manifestContent.layers.find(layer => layer.mediaType === 'application/vnd.ollama.image.model');
  if (!modelLayer) {
    console.warn(`[WARNING] No model layer found in manifest: ${relPath}`);
    if (isManual) process.exit(1);
    return;
  }

  const modelDigest = modelLayer.digest;
  const modelSha = modelDigest.replace('sha256:', '');
  const ggufBlobPath = path.join(ollamaBaseDir, 'models', 'blobs', `sha256-${modelSha}`);

  if (!fs.existsSync(ggufBlobPath)) {
    console.error(`[WARNING] GGUF blob file not found at: ${ggufBlobPath}`);
    if (isManual) process.exit(1);
    return;
  }

  console.log(`[INFO] Reviewing ${modelNameNormalized}...`);
  const parsed = await gguf(ggufBlobPath, { allowLocalFile: true });
  const metadata = parsed.metadata;

  const chatTemplate = metadata["tokenizer.chat_template"];
  if (!chatTemplate) {
    console.log(`[INFO] No tokenizer.chat_template in GGUF metadata for ${modelNameNormalized}. Skipping patch.`);
    if (isManual) process.exit(0);
    return;
  }

  console.log(`[INFO] Patching template for ${modelNameNormalized}...`);
  const ggufMetadata = {
    chat_template: chatTemplate,
    bos_token: metadata["tokenizer.ggml.bos_token_id"] || metadata["tokenizer.ggml.bos_token"] || undefined,
    eos_token: metadata["tokenizer.ggml.eos_token_id"] || metadata["tokenizer.ggml.eos_token"] || undefined,
  };

  const converted = convertGGUFTemplateToOllama(ggufMetadata);
  if (!converted || !converted.template) {
    console.warn(`[ERROR] Template conversion not supported or failed for ${modelNameNormalized}.`);
    if (isManual) process.exit(1);
    return;
  }

  let modelfileContent = `FROM ${modelNameNormalized}\n`;
  modelfileContent += `TEMPLATE """${converted.template}"""\n`;

  if (converted.params && converted.params.stop) {
    const stops = Array.isArray(converted.params.stop) ? converted.params.stop : [converted.params.stop];
    stops.forEach(stopToken => {
      modelfileContent += `PARAMETER stop "${stopToken}"\n`;
    });
  }

  const tempPath = path.join(__dirname, 'tmp_modelfile');
  fs.writeFileSync(tempPath, modelfileContent, 'utf8');

  console.log(`[INFO] Finalizing patch for '${modelNameNormalized}'...`);

  const createCmd = `/usr/bin/ollama create ${modelNameNormalized} -f ${tempPath}`;

  exec(createCmd, (error, stdout, stderr) => {
    if (fs.existsSync(tempPath)) {
      fs.unlinkSync(tempPath);
    }

    if (error) {
      console.error(`[ERROR] Failed to patch model:`, stderr || error.message);
      if (isManual) process.exit(1);
    } else {
      console.log(`[SUCCESS] Fully patched '${modelNameNormalized}' template!`);
      if (isManual) process.exit(0);
    }
  });
}
