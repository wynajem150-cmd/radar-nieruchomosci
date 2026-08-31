const regions = ["śląskie", "opolskie"];

Deno.serve(async (req) => {
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const authorization = req.headers.get("authorization") || "";
  const apikey = req.headers.get("apikey") || authorization.replace(/^Bearer\s+/i, "");
  const results = [];
  for (const region of regions) {
    try {
      const response = await fetch(`${supabaseUrl}/functions/v1/scan-wgn`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization, apikey },
        body: JSON.stringify({ region }),
      });
      results.push(await response.json());
    } catch (error) {
      results.push({ region, error: String(error) });
    }
  }
  return new Response(JSON.stringify({ ok: true, results }), {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
});
