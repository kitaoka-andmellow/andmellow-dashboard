import './globals.css';

export const metadata = {
  title: 'mellow 在庫管理',
  description: 'Amazon・楽天の販売SKUと単品在庫を管理するアプリ',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
