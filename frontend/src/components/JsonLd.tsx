import React from "react";

export default function JsonLd() {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": "https://nimbusagent.vercel.app/#software",
        "name": "Nimbus",
        "alternateName": "Nimbus Cloud Agent",
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Cloud-Native (Linux, Docker)",
        "description": "Autonomous cloud software engineering agent with zero-trust sandboxing, 3-tier multi-LLM resilient routing, and automated GitHub Pull Request generation.",
        "url": "https://nimbusagent.vercel.app",
        "author": {
          "@type": "Person",
          "name": "Anmol Sharma",
          "url": "https://anmolsharma152.vercel.app",
          "sameAs": [
            "https://github.com/anmolsharma152",
            "https://www.linkedin.com/in/anmolsharma152/"
          ]
        },
        "offers": {
          "@type": "Offer",
          "price": "0.00",
          "priceCurrency": "USD"
        }
      },
      {
        "@type": "Person",
        "@id": "https://anmolsharma152.vercel.app/#person",
        "name": "Anmol Sharma",
        "url": "https://anmolsharma152.vercel.app",
        "jobTitle": "AI Systems & Full-Stack Software Engineer",
        "sameAs": [
          "https://github.com/anmolsharma152",
          "https://www.linkedin.com/in/anmolsharma152/"
        ]
      }
    ]
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
    />
  );
}
