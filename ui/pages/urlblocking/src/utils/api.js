// Calls the `urlblock` cloud function and turns backend failures into exceptions.
//
// foundry-js resolves with the function payload ({ status_code, body, errors }) even when
// the handler answered 4xx/5xx, and rejects with a bare errors array when the execution
// itself fails. Every caller should go through here so failures are never shown as success.

function messageFrom(errors) {
  if (Array.isArray(errors) && errors.length) {
    return errors[0]?.message || String(errors[0]);
  }
  return null;
}

export async function callFunction(falcon, method, path, body) {
  const fn = falcon.cloudFunction({ name: 'urlblock', version: 1 }).path(path);
  let response;
  try {
    response = method === 'GET' ? await fn.get() : await fn.post(body ?? {});
  } catch (err) {
    throw new Error(messageFrom(err) || err?.message || 'Cloud function call failed');
  }

  const code = response?.status_code ?? response?.code;
  const failed = code !== undefined ? (code < 200 || code >= 300) : Boolean(response?.errors?.length);
  if (failed) {
    const message = messageFrom(response?.errors) || response?.body?.error || `Request failed (HTTP ${code})`;
    const error = new Error(message);
    error.status = code;
    error.body = response?.body;
    throw error;
  }
  return response?.body ?? {};
}
