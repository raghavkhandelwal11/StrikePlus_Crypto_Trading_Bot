// Map UI symbols → BSC token addresses. Mirrors backend orchestrator._SYMBOL_MAP.
export const SYMBOL_TO_TOKEN: Record<string, string> = {
  BNBUSDT: '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',     // WBNB
  BUSDUSDT: '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',    // BUSD
};

export function tokenForSymbol(symbol: string): string | undefined {
  return SYMBOL_TO_TOKEN[symbol];
}
