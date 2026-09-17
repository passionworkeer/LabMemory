// 画面分区：顶部固定标题带，录屏与图解内容都排在标题带下方，避免文字压到画面内容
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const HEADER_HEIGHT = 152;
export const CONTENT_TOP = HEADER_HEIGHT;
export const CONTENT_HEIGHT = FRAME_HEIGHT - CONTENT_TOP;
// 字幕条占用底部安全区，图解内容不进入该区域
export const DIAGRAM_ZONE = {top: 230, bottom: 850};
