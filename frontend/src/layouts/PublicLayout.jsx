import { useLocation } from "react-router-dom";
import { Footer } from "../components/layout/Footer.jsx";
import { Header } from "../components/layout/Header.jsx";

export default function PublicLayout({ children }) {
  const { pathname } = useLocation();
  const fullScreenEditor = pathname.startsWith("/create/design/");
  const adminWorkspace = pathname.startsWith("/admin");
  return (
    <>
      {!fullScreenEditor && !adminWorkspace ? <Header /> : null}
      {children}
      {!fullScreenEditor && !adminWorkspace ? <Footer /> : null}
    </>
  );
}
