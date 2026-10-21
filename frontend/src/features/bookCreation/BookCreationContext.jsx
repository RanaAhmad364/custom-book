import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";

const BookCreationContext = createContext(null);

const initialSelections = {
  startingOption: "template",
  selectedBook: null,
  selectedTemplate: null,
  title: "",
  bookSize: "10 × 10 in",
  pageCount: 24,
  coverType: "Hardcover",
  startingLayout: "Balanced story",
  photos: [],
};

export function BookCreationProvider({ children }) {
  const { user } = useAuth();
  const previousOwner = useRef(user?.email?.toLowerCase() ?? null);
  const [selections, setSelections] = useState(initialSelections);

  useEffect(() => {
    const nextOwner = user?.email?.toLowerCase() ?? null;
    if (previousOwner.current && previousOwner.current !== nextOwner) {
      setSelections(initialSelections);
    }
    previousOwner.current = nextOwner;
  }, [user?.email]);

  const updateSelections = useCallback((changes) => {
    setSelections((current) => ({ ...current, ...changes }));
  }, []);
  const begin = useCallback((changes) => {
    setSelections({ ...initialSelections, ...changes });
  }, []);
  const selectTemplate = useCallback((template) => {
    setSelections((current) => ({
      ...current,
      selectedBook: template,
      selectedTemplate: template,
      title: !current.title || current.title === current.selectedTemplate?.title ? template.title : current.title,
      bookSize: template.bookType === "LIGHT" ? "8 × 8 in" : "10 × 10 in",
      coverType: template.format || "Hardcover",
      startingOption: "template",
    }));
  }, []);
  const beginWithTemplate = useCallback((template) => {
    setSelections({
      ...initialSelections,
      selectedBook: template,
      selectedTemplate: template,
      title: template.title,
      bookSize: template.bookType === "LIGHT" ? "8 × 8 in" : "10 × 10 in",
      coverType: template.format || "Hardcover",
      startingOption: "template",
    });
  }, []);
  const addPhoto = useCallback((photo) => {
    setSelections((current) => ({ ...current, photos: [...current.photos, photo] }));
  }, []);
  const updatePhoto = useCallback((id, changes) => {
    setSelections((current) => ({
      ...current,
      photos: current.photos.map((photo) => photo.id === id ? { ...photo, ...changes } : photo),
    }));
  }, []);
  const removePhoto = useCallback((id) => {
    setSelections((current) => ({ ...current, photos: current.photos.filter((photo) => photo.id !== id) }));
  }, []);
  const reset = useCallback(() => {
    setSelections(initialSelections);
  }, []);
  const value = useMemo(() => ({
    selections,
    updateSelections,
    begin,
    selectTemplate,
    beginWithTemplate,
    addPhoto,
    updatePhoto,
    removePhoto,
    reset,
  }), [selections, updateSelections, begin, selectTemplate, beginWithTemplate, addPhoto, updatePhoto, removePhoto, reset]);

  return <BookCreationContext.Provider value={value}>{children}</BookCreationContext.Provider>;
}

export function useBookCreation() {
  const context = useContext(BookCreationContext);
  if (!context) throw new Error("useBookCreation must be used within BookCreationProvider.");
  return context;
}
