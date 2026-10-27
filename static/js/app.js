// ShifterSuivi : petits comportements de confort, sans dépendance.
(function () {
  "use strict";

  // Menu latéral sur mobile
  var boutonMenu = document.querySelector(".bouton-menu");
  if (boutonMenu) {
    boutonMenu.addEventListener("click", function () {
      var ouvert = document.body.classList.toggle("menu-ouvert");
      boutonMenu.setAttribute("aria-expanded", ouvert ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.body.classList.contains("menu-ouvert")) {
        document.body.classList.remove("menu-ouvert");
        boutonMenu.setAttribute("aria-expanded", "false");
        boutonMenu.focus();
      }
    });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("menu-ouvert") && !e.target.closest(".rail") && !e.target.closest(".bouton-menu")) {
        document.body.classList.remove("menu-ouvert");
        boutonMenu.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Confirmation avant les actions qui ne se défont pas
  document.addEventListener("submit", function (e) {
    var message = e.target.getAttribute("data-confirmer");
    if (message && !window.confirm(message)) {
      e.preventDefault();
    }
  });

  // Réception : client existant ou nouveau client
  var bascule = document.querySelectorAll('input[name="client_choix"]');
  function majClient() {
    var choix = document.querySelector('input[name="client_choix"]:checked');
    if (!choix) return;
    document.querySelectorAll("[data-bloc-client]").forEach(function (bloc) {
      var visible = bloc.getAttribute("data-bloc-client") === choix.value;
      bloc.hidden = !visible;
      bloc.querySelectorAll("input, select, textarea").forEach(function (champ) {
        champ.disabled = !visible;
      });
    });
  }
  bascule.forEach(function (radio) { radio.addEventListener("change", majClient); });
  majClient();

  // Accord immédiat : le moyen n'a de sens que si la case est cochée
  var accord = document.getElementById("id_o-accord_immediat");
  var moyen = document.querySelector("[data-moyen-accord]");
  if (accord && moyen) {
    var majAccord = function () { moyen.hidden = !accord.checked; };
    accord.addEventListener("change", majAccord);
    majAccord();
  }

  // Ligne d'intervention : taux horaire proposé, origine réservée aux pièces
  document.querySelectorAll("[data-form-ligne]").forEach(function (form) {
    var type = form.querySelector('[name="type_ligne"]');
    var prix = form.querySelector('[name="prix_unitaire_ht"]');
    var origine = form.querySelector("[data-champ-origine]");
    var taux = form.getAttribute("data-taux-horaire");
    function majType() {
      if (origine) origine.hidden = type.value !== "piece";
      if (type.value === "main_oeuvre" && prix && !prix.value && taux) prix.value = taux;
    }
    if (type) {
      type.addEventListener("change", majType);
      majType();
    }
  });

  // Photos : allégées dans le navigateur (1600 px, JPEG) avant l'envoi.
  // Un téléphone produit des photos de 3 à 6 Mo ; l'hébergeur refuse les envois de plus de 4,5 Mo.
  var COTE_MAX = 1600;

  function compresser(fichier) {
    if (!/^image\/(jpeg|png|webp)$/.test(fichier.type) || fichier.size < 350 * 1024 || !window.createImageBitmap) {
      return Promise.resolve(fichier);
    }
    return createImageBitmap(fichier).then(function (image) {
      var echelle = Math.min(1, COTE_MAX / Math.max(image.width, image.height));
      var toile = document.createElement("canvas");
      toile.width = Math.round(image.width * echelle);
      toile.height = Math.round(image.height * echelle);
      toile.getContext("2d").drawImage(image, 0, 0, toile.width, toile.height);
      return new Promise(function (resoudre) {
        toile.toBlob(function (blob) {
          if (!blob || blob.size >= fichier.size) return resoudre(fichier);
          var nom = fichier.name.replace(/\.(png|webp|jpe?g)$/i, "") + ".jpg";
          resoudre(new File([blob], nom, { type: "image/jpeg", lastModified: Date.now() }));
        }, "image/jpeg", 0.82);
      });
    }).catch(function () { return fichier; });
  }

  function taille(octets) {
    return octets < 1024 * 1024 ? Math.round(octets / 1024) + " Ko" : (octets / 1024 / 1024).toFixed(1).replace(".", ",") + " Mo";
  }

  document.querySelectorAll('input[type="file"]').forEach(function (champ) {
    var cible = document.getElementById(champ.id + "_liste");
    var boutons = champ.form ? champ.form.querySelectorAll('button[type="submit"], button:not([type])') : [];
    champ.addEventListener("change", function () {
      var fichiers = Array.prototype.slice.call(champ.files);
      if (!fichiers.length) {
        if (cible) cible.textContent = "Aucun fichier choisi";
        return;
      }
      if (cible) cible.textContent = "Préparation des photos…";
      boutons = Array.prototype.filter.call(boutons, function (b) { return !b.disabled; });
      boutons.forEach(function (b) { b.disabled = true; });
      Promise.all(fichiers.map(compresser)).then(function (prets) {
        if (window.DataTransfer) {
          var transfert = new DataTransfer();
          prets.forEach(function (f) { transfert.items.add(f); });
          champ.files = transfert.files;
        }
        var total = prets.reduce(function (s, f) { return s + f.size; }, 0);
        if (cible) cible.textContent = prets.length + " fichier(s), " + taille(total) + " : " + prets.map(function (f) { return f.name; }).join(", ");
      }).finally(function () {
        boutons.forEach(function (b) { b.disabled = false; });
        boutons = champ.form ? champ.form.querySelectorAll('button[type="submit"], button:not([type])') : [];
      });
    });
  });

  // Impression de la facture (ou enregistrement en PDF depuis le navigateur)
  document.querySelectorAll("[data-imprimer]").forEach(function (bouton) {
    bouton.addEventListener("click", function () { window.print(); });
  });

  // Filtres qui s'appliquent dès qu'on change la liste
  document.querySelectorAll("select[data-auto]").forEach(function (liste) {
    liste.addEventListener("change", function () { liste.form.submit(); });
  });
})();
