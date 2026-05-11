export default {
  async fetch(request, env) {
    // env.TOKEN — это переменная, которую вы создадите на следующем шаге
    return new Response(env.TOKEN || 'NO_LINK', {
      headers: { "content-type": "text/plain; charset=utf-8" }
    });
  }
}
