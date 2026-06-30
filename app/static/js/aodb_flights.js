/**
 * AODB Flight Autocomplete
 * Populates <datalist> elements with AODB flight numbers for a given date
 * and provides click-to-fill functionality for related form fields.
 */

(function () {
  const datalistAliasMaps = new WeakMap();

  /**
   * Initialize AODB flight autocomplete for inputs with data-aodb-autocomplete attribute.
   * Also provides "click-to-fill" buttons to pre-populate form fields from a flight.
   */
  async function initAodbAutocomplete() {
    // Populate datalists on page load
    const datalists = document.querySelectorAll('[data-aodb-datalist]');
    for (const dlist of datalists) {
      await populateFlightDatalist(dlist);

      // Normalize typed aliases (IATA/ICAO/base) to one canonical value.
      const listId = dlist.id;
      if (listId) {
        const linkedInputs = document.querySelectorAll(`input[list="${listId}"]`);
        linkedInputs.forEach((inp) => {
          const normalize = () => {
            const map = datalistAliasMaps.get(dlist) || new Map();
            const typed = (inp.value || '').replace(/\s+/g, '').toUpperCase();
            if (!typed) return;
            const canonical = map.get(typed);
            if (canonical) inp.value = canonical;
          };
          inp.addEventListener('change', normalize);
          inp.addEventListener('blur', normalize);
        });
      }

      const dateSourceSelector = dlist.dataset.aodbDateSource || '';
      if (dateSourceSelector) {
        const dateSource = document.querySelector(dateSourceSelector);
        if (dateSource) {
          dateSource.addEventListener('change', async () => {
            await populateFlightDatalist(dlist);
          });
        }
      }
    }

    // Wire up flight selection buttons (.use-flight-btn)
    document.querySelectorAll('.use-flight-btn').forEach((btn) => {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        const flight = btn.dataset.flight || '';
        const stand = btn.dataset.stand || '';
        if (flight) {
          const inp = document.querySelector('input[name="flight_number"]');
          if (inp) inp.value = flight;
        }
        if (stand) {
          const sel = document.querySelector('select[name="allocated_stand"]');
          if (sel) {
            for (let i = 0; i < sel.options.length; i++) {
              if (sel.options[i].value === stand) {
                sel.selectedIndex = i;
                break;
              }
            }
          }
        }
        // Auto-scroll to form
        const form = document.querySelector('[data-flight-form]');
        if (form) form.scrollIntoView({ behavior: 'smooth' });
      });
    });
  }

  /**
   * Fetch flights for a datalist and populate the <option> elements.
   */
  async function populateFlightDatalist(datalist) {
    let dateStr = datalist.dataset.aodbDate || '';
    const dateSourceSelector = datalist.dataset.aodbDateSource || '';
    if (dateSourceSelector) {
      const dateSource = document.querySelector(dateSourceSelector);
      if (dateSource && dateSource.value) {
        dateStr = dateSource.value;
      }
    }
    if (!dateStr) {
      dateStr = new Date().toISOString().split('T')[0];
    }
    const typeFilter = datalist.dataset.aodbType || 'all';

    try {
      const url = `/apron/api/flights?date=${dateStr}&type=${typeFilter}`;
      const resp = await fetch(url);
      if (!resp.ok) {
        console.warn(`Failed to fetch AODB flights: ${resp.status}`);
        return;
      }

      const flights = await resp.json();
      datalist.innerHTML = '';
      const aliasMap = new Map();
      const seenCanonical = new Set();
      flights.forEach((f) => {
        const base = (f.flight_number || '').trim();
        const iata = `${(f.flight_iata_code || '').trim()}${base}`.trim();
        const icao = `${(f.flight_icao_code || '').trim()}${base}`.trim();
        const variants = [icao, iata, base].filter((v) => !!v);
        if (!variants.length) return;

        const canonical = icao || iata || base;
        const canonicalKey = canonical.toUpperCase();
        variants.forEach((v) => aliasMap.set(v.toUpperCase(), canonical));
        if (seenCanonical.has(canonicalKey)) return;
        seenCanonical.add(canonicalKey);

        const labelCore = [icao || '-', iata || '-', base || '-'].join(' / ');
        const airline = (f.airline_name || f.airline || '').trim();
        const labelMeta = `${f.arr_or_dep || '-'} - ${airline}`.trim();

        const opt = document.createElement('option');
        opt.value = canonical;
        opt.label = `${labelCore} (${labelMeta})`;
        datalist.appendChild(opt);
      });
      datalistAliasMaps.set(datalist, aliasMap);
    } catch (err) {
      console.error('AODB datalist fetch error:', err);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAodbAutocomplete);
  } else {
    initAodbAutocomplete();
  }
})();
