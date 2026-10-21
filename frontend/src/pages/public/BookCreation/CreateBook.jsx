import { ArrowRight, Camera, FilePlus2, LayoutTemplate, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBookCreation } from "../../../features/bookCreation/BookCreationContext.jsx";
import { CreationHeading, CreationShell } from "./CreationShell.jsx";

const options = [
  { id: "template", icon: LayoutTemplate, title: "Use a template", text: "Begin with a considered design, ready for your photos.", action: "Choose a template", path: "/create/templates" },
  { id: "blank", icon: FilePlus2, title: "Start blank", text: "Shape every page from a clean, open canvas.", action: "Set up a blank book", path: "/create/setup" },
  { id: "quick", icon: Sparkles, title: "Quick start", text: "A few thoughtful defaults get your story moving.", action: "Get started quickly", path: "/create/photos" },
];

export default function CreateBook() {
  const { begin } = useBookCreation();
  const navigate = useNavigate();
  function choose(option) {
    if (option === "quick") {
      begin({ startingOption: "quick-start", title: "My MemoryBook" });
    } else {
      begin({ startingOption: option });
    }
    navigate(option === "template" ? "/create/templates" : option === "blank" ? "/create/setup" : "/create/photos");
  }

  return <CreationShell current="/create">
    <CreationHeading eyebrow="A story starts somewhere" title={<>What would you like<br /><em>to make today?</em></>} description="Choose the way you would like to begin. You can make every detail your own as you go." />
    <section className="creation-start-options" aria-label="Choose a way to start">
      {options.map(({ id, icon: Icon, title, text, action }) => <button className={`creation-start-card creation-start-${id}`} key={id} type="button" onClick={() => choose(id)}><span className="creation-option-icon"><Icon size={21} /></span><span className="creation-start-card-copy"><strong>{title}</strong><small>{text}</small><b>{action} <ArrowRight size={14} /></b></span>{id === "quick" ? <i>JUST A FEW STEPS</i> : null}</button>)}
    </section>
    <div className="creation-footnote"><Camera size={16} /><p>Your photos stay on this device in this preview. Sign in before creating to save your book to your account.</p></div>
  </CreationShell>;
}
