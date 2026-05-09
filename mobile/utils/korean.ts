const CHOSEONG = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'];

export function extractChoseong(text: string): string {
  return text
    .split('')
    .map((ch) => {
      const code = ch.charCodeAt(0);
      if (code >= 0xAC00 && code <= 0xD7A3) {
        return CHOSEONG[Math.floor((code - 0xAC00) / 588)];
      }
      return ch;
    })
    .join('');
}
