async function request(path, init = {}) {
    const resp = await fetch(path, {
        ...init,
        headers: {
            "Content-Type": "application/json",
            ...(init.headers ?? {}),
        },
    });
    if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`${resp.status} ${resp.statusText}: ${detail}`);
    }
    if (resp.status === 204)
        return undefined;
    return (await resp.json());
}
export const apiGet = (path) => request(path);
export const apiPost = (path, body) => request(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
});
export const apiPatch = (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) });
export const apiDelete = (path) => request(path, { method: "DELETE" });
