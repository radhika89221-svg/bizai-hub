export const getWebsiteOverview = (url) => {
  let hostname;

  // Safely parse the hostname so matching is not fooled by "amazonfake.com" etc.
  try {
    const parsed = new URL(url.startsWith("http") ? url : "https://" + url);
    hostname = parsed.hostname;
  } catch {
    return "This website contains multiple features. You can explore navigation, buttons, and content sections.";
  }

  if (hostname.includes("amazon.com")) {
    return "This is an e-commerce website. You can search products, add them to cart, and buy items.";
  }

  if (hostname.includes("youtube.com")) {
    return "This is a video platform. You can watch videos, search content, and subscribe to channels.";
  }

  if (hostname.includes("github.com")) {
    return "This is a developer platform. You can view code, repositories, and collaborate on projects.";
  }

  return "This website contains multiple features. You can explore navigation, buttons, and content sections.";
};