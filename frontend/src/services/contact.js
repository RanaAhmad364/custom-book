const previewDelay = (duration) =>
  new Promise((resolve) => window.setTimeout(resolve, duration));

export const contactService = {
  async submitMessage(message) {
    await previewDelay(500);
    if (!message.name || !message.email || !message.subject || !message.message) {
      throw new Error("Complete all required fields before continuing.");
    }

    return {
      validated: true,
      delivered: false,
      stored: false,
    };
  },
};
