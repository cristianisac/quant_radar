// plotly.js-dist-min ships without TS types. Re-declare as the same
// surface as @types/plotly.js — only the constructor/factory API is
// what we use, and react-plotly.js's factory accepts any Plotly-like.
declare module "plotly.js-dist-min" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Plotly: any;
  export default Plotly;
}
