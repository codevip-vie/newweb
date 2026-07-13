(function () {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    ready(function () {
        setupNavigation();
        setupSidebarToggle();
        setupThemeToggle();
        setupFlashDismiss();
        setupConfirmForms();
        setupImagePreviews();
        setupCarousels();
        setupScrollCarousels();
        setupUploadProgress();
    });

    function setupNavigation() {
        var toggle = document.querySelector("[data-nav-toggle]");
        var nav = document.querySelector("[data-site-nav]");
        if (!toggle || !nav) {
            return;
        }
        toggle.addEventListener("click", function () {
            var expanded = toggle.getAttribute("aria-expanded") === "true";
            toggle.setAttribute("aria-expanded", String(!expanded));
            nav.classList.toggle("is-open", !expanded);
        });
    }

    function setupSidebarToggle() {
        var toggle = document.querySelector("[data-sidebar-toggle]");
        var sidebar = document.querySelector(".site-sidebar");
        if (!toggle || !sidebar) {
            return;
        }

        toggle.addEventListener("click", function () {
            var expanded = toggle.getAttribute("aria-expanded") === "true";
            toggle.setAttribute("aria-expanded", String(!expanded));
            sidebar.classList.toggle("is-collapsed", expanded);
        });
    }

    function setupFlashDismiss() {
        document.querySelectorAll("[data-dismiss-flash]").forEach(function (button) {
            button.addEventListener("click", function () {
                var flash = button.closest(".flash");
                if (flash) {
                    flash.remove();
                }
            });
        });
    }

    function setupConfirmForms() {
        document.querySelectorAll("form[data-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (!window.confirm(form.getAttribute("data-confirm"))) {
                    event.preventDefault();
                }
            });
        });
    }

    function setupImagePreviews() {
        document.querySelectorAll("input[type='file'][data-preview-target]").forEach(function (input) {
            input.addEventListener("change", function () {
                var targetId = input.getAttribute("data-preview-target");
                var preview = targetId ? document.getElementById(targetId) : null;
                var file = input.files && input.files[0];
                if (!preview || !file) {
                    return;
                }
                var filename = file.name || "";
                var isImage = (file.type && file.type.startsWith("image/")) || /\.(png|jpe?g)$/i.test(filename);
                if (!isImage) {
                    preview.hidden = true;
                    preview.removeAttribute("src");
                    return;
                }
                preview.src = URL.createObjectURL(file);
                preview.hidden = false;
                preview.removeAttribute("hidden");
            });
        });
    }

    function setupCarousels() {
        document.querySelectorAll("[data-carousel]").forEach(function (carousel) {
            var slides = Array.prototype.slice.call(carousel.querySelectorAll(".hero-slide"));
            if (slides.length <= 1) {
                return;
            }

            var index = slides.findIndex(function (slide) {
                return slide.classList.contains("is-active");
            });
            if (index < 0) {
                index = 0;
            }

            var dotsWrap = carousel.querySelector("[data-carousel-dots]");
            var dots = [];
            if (dotsWrap) {
                slides.forEach(function (_slide, dotIndex) {
                    var dot = document.createElement("button");
                    dot.type = "button";
                    dot.className = "carousel-dot";
                    dot.setAttribute("aria-label", "Go to slide " + (dotIndex + 1));
                    dot.addEventListener("click", function () {
                        show(dotIndex);
                    });
                    dotsWrap.appendChild(dot);
                    dots.push(dot);
                });
            }

            function show(nextIndex) {
                slides[index].classList.remove("is-active");
                if (dots[index]) {
                    dots[index].classList.remove("is-active");
                }
                index = (nextIndex + slides.length) % slides.length;
                slides[index].classList.add("is-active");
                if (dots[index]) {
                    dots[index].classList.add("is-active");
                }
            }

            var prev = carousel.querySelector("[data-carousel-prev]");
            var next = carousel.querySelector("[data-carousel-next]");
            if (prev) {
                prev.addEventListener("click", function () {
                    show(index - 1);
                });
            }
            if (next) {
                next.addEventListener("click", function () {
                    show(index + 1);
                });
            }

            show(index);
            if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
                window.setInterval(function () {
                    show(index + 1);
                }, 6500);
            }
        });
    }

    function setupScrollCarousels() {
        document.querySelectorAll("[data-scroll-carousel]").forEach(function (carousel) {
            var container = carousel.querySelector("[data-scroll-container]");
            var prev = carousel.querySelector(".carousel-arrow.prev");
            var next = carousel.querySelector(".carousel-arrow.next");
            if (!container) {
                return;
            }
            function scrollByWidth(direction) {
                var amount = container.clientWidth * 0.85;
                container.scrollBy({ left: amount * direction, behavior: "smooth" });
            }
            if (prev) {
                prev.addEventListener("click", function () {
                    scrollByWidth(-1);
                });
            }
            if (next) {
                next.addEventListener("click", function () {
                    scrollByWidth(1);
                });
            }
        });
    }

    function setupThemeToggle() {
        var button = document.querySelector("[data-theme-toggle]");
        if (!button) {
            return;
        }

        function setTheme(theme) {
            document.body.setAttribute("data-theme", theme);
            localStorage.setItem("siteTheme", theme);
            button.textContent = theme === "light" ? "🌙" : "🌗";
        }

        var storedTheme = localStorage.getItem("siteTheme");
        setTheme(storedTheme === "light" ? "light" : "dark");

        button.addEventListener("click", function () {
            var currentTheme = document.body.getAttribute("data-theme");
            setTheme(currentTheme === "light" ? "dark" : "light");
        });
    }

    function setupUploadProgress() {
        document.querySelectorAll("form[data-upload-progress]").forEach(function (form) {
            if (!window.FormData || !window.XMLHttpRequest) {
                return;
            }

            form.addEventListener("submit", function (event) {
                event.preventDefault();

                var submitButton = form.querySelector("button[type='submit']");
                var progressShell = form.querySelector("[data-progress-shell]");
                var progressBar = form.querySelector("[data-progress-bar]");
                var progressLabel = form.querySelector("[data-progress-label]");
                var errorBox = document.querySelector("[data-form-errors]");

                if (errorBox) {
                    errorBox.hidden = true;
                    errorBox.innerHTML = "";
                }
                if (progressShell) {
                    progressShell.hidden = false;
                }
                if (submitButton) {
                    submitButton.disabled = true;
                }

                var xhr = new XMLHttpRequest();
                xhr.open(form.method || "POST", form.action || window.location.href);
                xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");

                xhr.upload.addEventListener("progress", function (event) {
                    if (!event.lengthComputable || !progressBar || !progressLabel) {
                        return;
                    }
                    var percent = Math.round((event.loaded / event.total) * 100);
                    progressBar.style.width = percent + "%";
                    progressLabel.textContent = "Uploading " + percent + "%";
                });

                xhr.addEventListener("load", function () {
                    var response = parseJson(xhr.responseText);
                    if (xhr.status >= 200 && xhr.status < 300 && response && response.ok) {
                        window.location.assign(response.redirect);
                        return;
                    }
                    if (response && response.errors && errorBox) {
                        errorBox.innerHTML = response.errors.map(function (error) {
                            return "<p>" + escapeHtml(error) + "</p>";
                        }).join("");
                        errorBox.hidden = false;
                    } else if (errorBox) {
                        errorBox.innerHTML = "<p>Upload failed. Please try again.</p>";
                        errorBox.hidden = false;
                    }
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                });

                xhr.addEventListener("error", function () {
                    if (errorBox) {
                        errorBox.innerHTML = "<p>Network error while uploading.</p>";
                        errorBox.hidden = false;
                    }
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                });

                xhr.send(new FormData(form));
            });
        });
    }

    function parseJson(text) {
        try {
            return JSON.parse(text);
        } catch (error) {
            return null;
        }
    }

    function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, function (character) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                "\"": "&quot;",
                "'": "&#039;"
            }[character];
        });
    }
}());
