"""
Home Assistant / MQTT discovery profile for the verified boiler profile:

  Viessmann Vitodens 200-W WB2A
  VDensHO1 / device id 0x20C2
  software index 0x03

This is the live image profile installed as /opt/optolink/homeassistant_poll_list.py.
The legacy /opt/optolink/poll_list.py is removed when this profile is applied
because optolink-splitter gives poll_list.py precedence over the HA adapter.

Hardware research source of truth:
  vdensho1-20c2-wb2a-service-draft-poll-list.py

Policy used here:
  * expose hardware-verified read datapoints;
  * expose writes only where this exact appliance has accepted the write and
    the resulting controller state has been verified;
  * keep absent hardware (M2, solar, hydraulic separator, invalid sensor
    inputs) out of productive polling;
  * keep diagnostics/service values enabled for use in dashboards/automations, but hidden by default from generated UI where possible;
  * do not expose burner unlock/reset;
  * do not expose economy mode as a switch: 0x2302 write ACKs but is ignored.

Write verification on this exact appliance:
  0x2303 native party state: readable; remote OFF is reliable, but remote ON is
    not reliable after Party is switched off at the physical control panel.
    Production Party activation therefore does not write 0x2303=1.
  0x2306 normal room target: R/W
  0x2307 reduced room target: R/W
  0x2308 party room target: R/W
  0x2323 operating mode: R/W verified for values 2 and 4; synthetic Party
    uses value 4 (Dauernd Normal) and restores the previous value afterwards
  synthetic Party end-to-end: verified with distinct setpoints (0x2306=21 C,
    0x2308=22 C): ON mirrored 22 C to 0x2306 and set 0x2323=4; OFF restored
    0x2306=21 C and 0x2323=2. Native physical Party still tracks through 0x2303.
  0x6300 DHW target: R/W, current configured range 10..60 C
  0x6773 circulation interval: R/W verified for values 0 and 7

Writable selects expose the complete VDensHO1 source-documented enums.
Hardware write tests on this exact appliance have so far covered 0x2323
values 2 and 4, and 0x6773 values 0 and 7.
"""

poll_list = {
    "device": {
        "identifiers": ["viessmann_vitodens_200_w_wb2a_20c2"],
        "name": "Vitodens 200-W WB2A",
        "model": "Vitodens 200-W WB2A",
        "manufacturer": "Viessmann",
        "hw_version": "20C2",
        "sw_version": "VDensHO1 SW03",
    },

    "node_id": "vitodens_200_w_wb2a_20c2",
    "dp_prefix": "vitodens_200_wb2a_",

    "beautifier": {
        "search": [
            "aussentemperatur", "kessel", "warmwasser", "heizkreis_m1",
            "brenner", "pumpe", "zirkulation", "betriebsart", "solltemperatur",
            "temperatur", "geblaese", "ueber", "stoer", "geraete"
        ],
        "replace": [
            "außentemperatur", "kessel", "warmwasser", "heizkreis m1",
            "brenner", "pumpe", "zirkulation", "betriebsart", "solltemperatur",
            "temperatur", "gebläse", "über", "stör", "geräte"
        ],
        "fixed": ["WW", "A1", "M1", "K12", "GFA", "SW", "BLR", "CFDM", "RKR"],
    },

    # Continuous cycle scheduling. The local phased-scheduler patch keeps
    # olbreath between every real Optolink transaction and distributes the
    # slower groups across their period instead of bunching them into one
    # long cycle.
    "poll_interval": 0,
    "poll_groups": {
        "ONCE": 0,       # exactly once per splitter process start
        "FAST": 1,       # every completed poll cycle
        "NORMAL": 5,     # approximately every 5 FAST cycles
        "DIAG": 15,      # internal control diagnostics
        "SLOW": 150,     # sensor/EEPROM health; roughly several minutes
        "RARE": 900,     # counters/error history; roughly tens of minutes
        "DISABLED": -1,
    },

    "mqtt_delay": 0.15,

    "domains": [
        # -----------------------------------------------------------------
        # Temperatures
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "suggested_display_precision": 1,
            "poll": [
                ("NORMAL",   "aussentemperatur",                   0x0800, 2, 0.1, True),
                ("SLOW", "aussentemperatur_tiefpass",          0x5525, 2, 0.1, True),
                ("SLOW", "aussentemperatur_gedaempft",         0x5527, 2, 0.1, True),
                ("FAST",   "kesseltemperatur",                   0x0810, 2, 0.1, True),
                ("FAST",   "kessel_solltemperatur_effektiv",     0x555A, 2, 0.1, True),
                ("NORMAL", "abgastemperatur",                    0x0816, 2, 0.1, True),
                ("FAST",   "warmwasser_temperatur",              0x0812, 2, 0.1, True),
                ("NORMAL", "warmwasser_solltemperatur_aktuell",  0x6500, 2, 0.1, True),
                ("FAST",   "heizkreis_m1_vorlauftemperatur",     0x2900, 2, 0.1, True),
                ("FAST",   "heizkreis_m1_vorlaufsolltemperatur", 0x2544, 2, 0.1, True),
                ("NORMAL", "heizkreis_m1_raumsolltemperatur_aktuell",
                                                                  0x2500, 22, "b:12:13", 0.1, True),
            ],
        },

        # -----------------------------------------------------------------
        # Percentages
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "suggested_display_precision": 0,
            "poll": [
                ("FAST", "brenner_modulationsgrad",         0xA305, 1, 0.5, False),
                ("FAST", "interne_pumpe_drehzahl",          0x7660, 2, "b:1:1", 1, False),
                ("FAST", "heizkreis_m1_pumpe_drehzahl",     0x7663, 2, "b:1:1", 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Feuerungsautomat / GFA direct VS1 reads.
        #
        # Hardware-validated on this exact WB2A using persistent VS1:
        #   P80 0x4050 = 0x20 local GFA branch identity
        #   P06 0x4006 = controller-reported fan speed, x30 rpm
        #   P09 0x4009 = GFA modulation setpoint, x0.3922 %
        #   P87 0x4057 = GFA Status 3 raw byte; bit semantics unresolved
        #
        # The runtime integration treats "gfa:<format>" as read-only 0x6B.
        # P80 MUST stay before P06/P09/P87. Productive GFA polling is guarded
        # by the last successful P80=20 identity observation.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:identifier",
            "poll": [
                ("FAST", "gfa_p80_typ", 0x4050, 1, "gfa:raw", False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "rpm",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:fan",
            "suggested_display_precision": 0,
            "poll": [
                ("FAST", "geblaesedrehzahl_gfa_p06", 0x4006, 1, "gfa:30", False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:gauge",
            "suggested_display_precision": 1,
            "poll": [
                ("FAST", "gfa_modulationssollwert_p09", 0x4009, 1, "gfa:0.3922", False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:code-tags",
            "poll": [
                ("FAST", "gfa_status3_p87", 0x4057, 1, "gfa:raw", False),
            ],
        },

        # -----------------------------------------------------------------
        # Counters
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "state_class": "total_increasing",
            "icon": "mdi:counter",
            "poll": [
                ("RARE", "brenner_starts", 0x088A, 4, 1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "h",
            "device_class": "duration",
            "state_class": "total_increasing",
            "suggested_display_precision": 1,
            "units": [
                {
                    "poll": [
                        ("RARE", "brenner_betriebsstunden", 0x08A7, 4, 0.0002777777777777778, False),
                    ],
                },
                {
                    "enabled_by_default": True,
                    "poll": [
                        ("RARE", "brenner_betriebsstunden_stufe1", 0x0886, 4, 0.0002777777777777778, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Maintenance / service diagnostics
        #
        # Exact VDensHO1 metadata + local validation on 2026-09-24:
        #   0x5721 len1: maintenance burner-runtime threshold, raw * 100 h
        #   0x5723 len1: maintenance interval in months; local R/W verified
        #   0x5724 len1: maintenance status, 0=Grundzustand / 1=Wartung
        #   0x756C len4: read-only LastCheckInterval reference storage
        #   0x7570 len4: read-only LastBurnerCheck reference storage
        #
        # Important correction from the live 0x5723 write probe:
        # 0x756C is NOT a plain elapsed-month counter. It changed to a
        # little-endian Unix-seconds reference timestamp whenever 0x5723 was
        # changed. 0x7570 likewise has a Vitosoft custom conversion and must
        # not be exposed as direct elapsed hours until LastBurnerCheck is
        # reconstructed.
        #
        # Production remains READ ONLY for maintenance control: no command
        # topic and no maintenance-reset control yet.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "unit_of_measurement": "h",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:wrench-clock",
            "suggested_display_precision": 0,
            "poll": [
                ("RARE", "wartung_brennerstunden_grenzwert", 0x5721, 1, 100, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "Monate",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:calendar-clock",
            "suggested_display_precision": 0,
            "poll": [
                ("RARE", "wartung_zeitintervall", 0x5723, 1, 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:database-clock",
            "poll": [
                ("RARE", "wartung_intervall_referenz_raw", 0x756C, 4, "raw", False),
                ("RARE", "wartung_brenner_referenz_raw", 0x7570, 4, "raw", False),
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "1",
            "payload_off": "0",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:wrench",
            "poll": [
                ("RARE", "wartung_status", 0x5724, 1, 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Binary status: numeric 0/1
        # -----------------------------------------------------------------
        {
            "domain": "binary_sensor",
            "payload_on": "1",
            "payload_off": "0",
            "poll": [
                ("FAST",   "interne_pumpe_status",              0x7660, 2, "b:0:0", 1, False),
                ("FAST",   "heizkreis_m1_pumpe_ausgang",        0x7663, 2, "b:0:0", 1, False),
                ("FAST",   "heizkreis_m1_pumpe_logisch",        0x2906, 1, 1, False),
                ("FAST",   "speicherladepumpe_status",          0x6513, 1, 1, False),
                ("NORMAL",   "zirkulationspumpe_status",          0x6515, 1, 1, False),
                ("FAST", "warmwasser_flowswitch",             0x0883, 1, 1, False),
                ("NORMAL", "heizkreis_m1_sparbetrieb",          0x2302, 1, 1, False),
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "1",
            "payload_off": "0",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "poll": [
                ("NORMAL", "relais_k12_status", 0x0842, 1, 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Fire-control diagnostic block (shared 0x55D3 read)
        #
        # Hardware-verified on this WB2A / VDensHO1:
        #   byte 5 bit 0x20  = flame
        #   byte 5 bit 0x40  = fire-control lockout
        #   bytes 6..7       = runtime-state bytes; the earlier blower-rpm
        #                      interpretation was rejected by live captures.
        #
        # Keep flame and lockout consecutive so the same response can be reused.
        # -----------------------------------------------------------------
        {
            "domain": "binary_sensor",
            "payload_on": "True",
            "payload_off": "False",
            "icon": "mdi:fire",
            "poll": [
                ("FAST", "brenner_flamme", 0x55D3, 9, "b:5:5:0x20", "bool", False),
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "True",
            "payload_off": "False",
            "device_class": "problem",
            "entity_category": "diagnostic",
            "poll": [
                ("FAST", "feuerungsautomat_verriegelt", 0x55D3, 9, "b:5:5:0x40", "bool", False),
            ],
        },

        # -----------------------------------------------------------------
        # Other bit-filtered binary status
        # -----------------------------------------------------------------
        {
            "domain": "binary_sensor",
            "payload_on": "True",
            "payload_off": "False",
            "poll": [
                ("SLOW", "heizkreis_m1_frostgefahr",  0x2500, 22, "b:16:16:0x01", "bool", False),
                ("SLOW", "heizkreis_m1_ferienbetrieb", 0x2535, 1, "b:0:0:0x01", "bool", False),
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "True",
            "payload_off": "False",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "poll": [
                ("NORMAL", "brenner_flamme_gfa", 0x55DD, 1, "b:0:0:0x20", "bool", False),
            ],
        },

        # -----------------------------------------------------------------
        # Party mode: persistent synthetic control for VDensHO1 / 20C2 / SW03.
        #
        # Native 0x2303=1 is not a reliable remote activation path on this
        # controller after Party has been switched off at the physical panel.
        # The companion optolink-party-emulator service therefore:
        #   * stores the current 0x2323 mode and 0x2306 normal setpoint;
        #   * mirrors 0x2308 Party setpoint to 0x2306 while active;
        #   * forces 0x2323=4 (Dauernd Normal);
        #   * restores both previous values on Party OFF;
        #   * applies the configured 0x27F2 time limit;
        #   * still recognizes native physical Party via 0x2303.
        #
        # Keep the existing entity name/unique_id so the dashboard does not
        # need to change.
        # -----------------------------------------------------------------
        {
            "domain": "switch",
            "icon": "mdi:party-popper",
            "command_topic": "{mqtt_base}/party_emulation/set",
            "state_topic": "{mqtt_base}/party_emulation/state",
            "payload_on": "1",
            "payload_off": "0",
            "state_on": "1",
            "state_off": "0",
            "optimistic": False,
            "nopoll": [
                {
                    "name": "heizkreis_m1_partybetrieb",
                },
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:party-popper",
            "nopoll": [
                {
                    "name": "heizkreis_m1_party_emulation_status",
                    "state_topic": "{mqtt_base}/party_emulation/status",
                    "value_template": "{{ value_json.mode }}",
                    "json_attributes_topic": "{mqtt_base}/party_emulation/status",
                },
            ],
        },

        # -----------------------------------------------------------------
        # Writable room/DHW setpoints: all hardware-verified R/W
        # -----------------------------------------------------------------
        {
            "domain": "number",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "suggested_display_precision": 0,
            "step": 1,
            "mode": "box",
            "command_topic": "%mqtt_listen%",
            "command_template": "{{ 'w;%DpAddr%;%Length%;' ~ (value | int) }}",
            "units": [
                {
                    "min": 3,
                    "max": 37,
                    "poll": [
                        ("NORMAL", "heizkreis_m1_raumsolltemperatur_normal",     0x2306, 1, 1, False),
                        ("NORMAL", "heizkreis_m1_raumsolltemperatur_reduziert", 0x2307, 1, 1, False),
                        ("NORMAL", "heizkreis_m1_raumsolltemperatur_party",     0x2308, 1, 1, False),
                    ],
                },
                {
                    # 0x6756=0 configures the user range to 10..60 C.
                    # Coding-plug capability at 0x1050 is 10..63 C.
                    "min": 10,
                    "max": 60,
                    "poll": [
                        ("NORMAL", "warmwasser_solltemperatur", 0x6300, 1, 1, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Operating mode 0x2323.
        # Exact VDensHO1 enum. Hardware writes verified on this unit for 2 <-> 4.
        # -----------------------------------------------------------------
        {
            "domain": "select",
            "options": [
                "Abschalt",
                "Nur WW",
                "Heizen + WW",
                "Dauernd Reduziert",
                "Dauernd Normal",
            ],
            "command_topic": "%mqtt_listen%",
            "command_template": "{% if value == 'Abschalt' %}w;%DpAddr%;%Length%;0{% elif value == 'Nur WW' %}w;%DpAddr%;%Length%;1{% elif value == 'Heizen + WW' %}w;%DpAddr%;%Length%;2{% elif value == 'Dauernd Reduziert' %}w;%DpAddr%;%Length%;3{% elif value == 'Dauernd Normal' %}w;%DpAddr%;%Length%;4{% endif %}",
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Abschalt{% elif v == 1 %}Nur WW{% elif v == 2 %}Heizen + WW{% elif v == 3 %}Dauernd Reduziert{% elif v == 4 %}Dauernd Normal{% else %}Unbekannt ({{ v }}){% endif %}",
            "optimistic": False,
            "poll": [
                ("NORMAL", "heizkreis_m1_betriebsart", 0x2323, 1, 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Circulation interval 0x6773.
        # Exact VDensHO1 enum. Hardware writes verified on this unit for 0 <-> 7.
        # -----------------------------------------------------------------
        {
            "domain": "select",
            "options": [
                "Schaltuhr",
                "1 pro Stunde",
                "2 pro Stunde",
                "3 pro Stunde",
                "4 pro Stunde",
                "5 pro Stunde",
                "6 pro Stunde",
                "EIN",
            ],
            "command_topic": "%mqtt_listen%",
            "command_template": "{% if value == 'Schaltuhr' %}w;%DpAddr%;%Length%;0{% elif value == '1 pro Stunde' %}w;%DpAddr%;%Length%;1{% elif value == '2 pro Stunde' %}w;%DpAddr%;%Length%;2{% elif value == '3 pro Stunde' %}w;%DpAddr%;%Length%;3{% elif value == '4 pro Stunde' %}w;%DpAddr%;%Length%;4{% elif value == '5 pro Stunde' %}w;%DpAddr%;%Length%;5{% elif value == '6 pro Stunde' %}w;%DpAddr%;%Length%;6{% elif value == 'EIN' %}w;%DpAddr%;%Length%;7{% endif %}",
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Schaltuhr{% elif v == 1 %}1 pro Stunde{% elif v == 2 %}2 pro Stunde{% elif v == 3 %}3 pro Stunde{% elif v == 4 %}4 pro Stunde{% elif v == 5 %}5 pro Stunde{% elif v == 6 %}6 pro Stunde{% elif v == 7 %}EIN{% else %}Unbekannt ({{ v }}){% endif %}",
            "optimistic": False,
            "poll": [
                ("NORMAL", "zirkulation_intervall", 0x6773, 1, 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Service/config controls used by the Home Assistant dashboard.
        #
        # These controls reuse already-polled datapoints via MQTT /set topics,
        # so they add no duplicate Optolink reads. The ranges below follow the
        # VDensHO1/Viessmann coding documentation. They are source-documented
        # R/W controls, but (unless noted above) have not all been hardware-
        # write-tested on this exact appliance.
        # -----------------------------------------------------------------
        {
            "domain": "number",
            "entity_category": "config",
            "mode": "box",
            "units": [
                {
                    "min": 0.2,
                    "max": 3.5,
                    "step": 0.1,
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_heizkennlinie_neigung_d3_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_heizkennlinie_neigung_d3",
                            "command_topic": "{mqtt_base}/heizkreis_m1_heizkennlinie_neigung_d3/set",
                        },
                    ],
                },
                {
                    "min": -13,
                    "max": 40,
                    "step": 1,
                    "unit_of_measurement": "K",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_heizkennlinie_niveau_d4_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_heizkennlinie_niveau_d4",
                            "command_topic": "{mqtt_base}/heizkreis_m1_heizkennlinie_niveau_d4/set",
                        },
                    ],
                },
                {
                    "min": -9,
                    "max": 15,
                    "step": 1,
                    "unit_of_measurement": "°C",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_frostgrenze_a3_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_frostgrenze_a3",
                            "command_topic": "{mqtt_base}/heizkreis_m1_frostgrenze_a3/set",
                        },
                    ],
                },
                {
                    "min": 0,
                    "max": 15,
                    "step": 1,
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_sommerspar_schaltschwelle_a5_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_sommerspar_schaltschwelle_a5",
                            "command_topic": "{mqtt_base}/heizkreis_m1_sommerspar_schaltschwelle_a5/set",
                        },
                    ],
                },
                {
                    "min": 5,
                    "max": 36,
                    "step": 1,
                    "unit_of_measurement": "°C",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_sommersparabschaltung_a6_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_sommersparabschaltung_a6",
                            "command_topic": "{mqtt_base}/heizkreis_m1_sommersparabschaltung_a6/set",
                        },
                    ],
                },
                {
                    "min": 1,
                    "max": 127,
                    "step": 1,
                    "unit_of_measurement": "°C",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_vorlauf_min_c5_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_vorlauf_min_c5",
                            "command_topic": "{mqtt_base}/heizkreis_m1_vorlauf_min_c5/set",
                        },
                    ],
                },
                {
                    "min": 10,
                    "max": 127,
                    "step": 1,
                    "unit_of_measurement": "°C",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_vorlauf_max_c6_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_vorlauf_max_c6",
                            "command_topic": "{mqtt_base}/heizkreis_m1_vorlauf_max_c6/set",
                        },
                    ],
                },
                {
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "unit_of_measurement": "%",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_pumpe_max_drehzahl_e6_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_pumpe_max_drehzahl_e6",
                            "command_topic": "{mqtt_base}/heizkreis_m1_pumpe_max_drehzahl_e6/set",
                        },
                        {
                            "name": "heizkreis_m1_pumpe_min_drehzahl_e7_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_pumpe_min_drehzahl_e7",
                            "command_topic": "{mqtt_base}/heizkreis_m1_pumpe_min_drehzahl_e7/set",
                        },
                        {
                            "name": "heizkreis_m1_pumpe_reduziert_e9_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_pumpe_reduziert_e9",
                            "command_topic": "{mqtt_base}/heizkreis_m1_pumpe_reduziert_e9/set",
                        },
                        {
                            "name": "interne_pumpe_solldrehzahl_31_einstellung",
                            "state_topic": "{mqtt_base}/interne_pumpe_solldrehzahl_31",
                            "command_topic": "{mqtt_base}/interne_pumpe_solldrehzahl_31/set",
                        },
                    ],
                },
                {
                    "min": 0,
                    "max": 15,
                    "step": 1,
                    "unit_of_measurement": "min",
                    "nopoll": [
                        {
                            "name": "heizkreis_m1_pumpe_reduziert_a9_einstellung",
                            "state_topic": "{mqtt_base}/heizkreis_m1_pumpe_reduziert_a9",
                            "command_topic": "{mqtt_base}/heizkreis_m1_pumpe_reduziert_a9/set",
                        },
                        {
                            "name": "warmwasser_pumpennachlauf_62_einstellung",
                            "state_topic": "{mqtt_base}/warmwasser_pumpennachlauf_62",
                            "command_topic": "{mqtt_base}/warmwasser_pumpennachlauf_62/set",
                        },
                    ],
                },
                {
                    "min": 5,
                    "max": 25,
                    "step": 1,
                    "unit_of_measurement": "K",
                    "nopoll": [
                        {
                            "name": "warmwasser_kessel_offset_60_einstellung",
                            "state_topic": "{mqtt_base}/warmwasser_kessel_offset_60",
                            "command_topic": "{mqtt_base}/warmwasser_kessel_offset_60/set",
                        },
                    ],
                },
            ],
        },
        {
            "domain": "select",
            "entity_category": "config",
            "options": [
                "Minimum nach E7",
                "Reduziert nach E9",
            ],
            "command_template": "{% if value == 'Minimum nach E7' %}0{% elif value == 'Reduziert nach E9' %}1{% endif %}",
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Minimum nach E7{% elif v == 1 %}Reduziert nach E9{% else %}Unbekannt ({{ v }}){% endif %}",
            "nopoll": [
                {
                    "name": "heizkreis_m1_pumpe_nebenbetrieb_e8_einstellung",
                    "state_topic": "{mqtt_base}/heizkreis_m1_pumpe_nebenbetrieb_e8",
                    "command_topic": "{mqtt_base}/heizkreis_m1_pumpe_nebenbetrieb_e8/set",
                },
            ],
        },
        # -----------------------------------------------------------------
        # Dashboard aliases for service values.
        # These use new unique_ids so existing HA registry entries that were
        # previously disabled do not suppress the dashboard values.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "nopoll": [
                {
                    "name": "interne_pumpe_kennung_30_anzeige",
                    "state_topic": "{mqtt_base}/interne_pumpe_kennung_30",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 1 %}Drehzahlgeregelt{% elif v == 0 %}Stufig{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "warmwasser_sollbereich_56_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_sollbereich_56",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}10–60 °C{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "warmwasser_einschalt_offset_59_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_einschalt_offset_59",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}2,5 K unter Soll{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "umschaltventil_bauart_65_anzeige",
                    "state_topic": "{mqtt_base}/umschaltventil_bauart_65",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 3 %}Grundfos Ventil{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "zirkulation_bei_ww_soll1_71_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_bei_ww_soll1_71",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Regelfunktion{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "zirkulation_bei_ww_soll2_72_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_bei_ww_soll2_72",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Regelfunktion{% else %}Wert {{ v }}{% endif %}",
                },
            ],
        },

        # -----------------------------------------------------------------
        # Enumerated operating/status sensors
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "poll": [],
            "units": [
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Abschaltbetrieb{% elif v == 1 %}Reduzierter Betrieb{% elif v == 2 %}Normalbetrieb{% elif v == 3 %}Dauernd Normal{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("NORMAL", "heizkreis_m1_betriebsart_aktuell", 0x2500, 22, "b:1:1", 1, False),
                    ],
                },
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 2 %}Normal dauernd{% elif v == 3 %}Heizen + WW Schaltzeiten{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("NORMAL", "heizkreis_m1_betriebsprogramm_aktuell", 0x2301, 1, 1, False),
                    ],
                },
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Ladung inaktiv{% elif v == 1 %}In Ladung{% elif v == 2 %}Im Nachlauf{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("FAST", "warmwasser_ladestatus", 0x650A, 1, 1, False),
                    ],
                },
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Undefiniert{% elif v == 1 %}Richtung Heizen{% elif v == 2 %}Mittelstellung{% elif v == 3 %}Richtung Warmwasser{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("FAST", "umschaltventil_stellung", 0x0A10, 1, 1, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Sensor/control diagnostics
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "units": [
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("SLOW", "sensorstatus_aussentemperatur", 0x083A, 1, 1, False),
                        ("SLOW", "sensorstatus_kesseltemperatur", 0x083B, 1, 1, False),
                        ("SLOW", "sensorstatus_sts2",             0x083D, 1, 1, False),
                        ("SLOW", "sensorstatus_vlts",             0x0840, 1, 1, False),
                        ("SLOW", "sensorstatus_raum_m1",          0x089C, 1, 1, False),
                    ],
                },
                {
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Konstantregelung{% elif v == 1 %}VT-Soll über LON{% elif v == 2 %}Witterungsgeführt{% elif v == 3 %}Raumregelung{% elif v == 4 %}Estrichprogramm{% elif v == 5 %}Heizkreis nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                    "poll": [
                        ("ONCE", "heizkreis_m1_reglervariante", 0x2521, 1, 1, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Service values - read only, diagnostic, enabled but hidden by default.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "units": [
                {
                    "unit_of_measurement": "°C",
                    "poll": [
                        ("ONCE", "heizkreis_m1_frostgrenze_a3", 0x27A3, 1, 1, True),
                        ("ONCE", "heizkreis_m1_sommersparabschaltung_a6", 0x27A6, 1, 1, False),
                        ("ONCE", "heizkreis_m1_vorlauf_min_c5", 0x27C5, 1, 1, False),
                        ("ONCE", "heizkreis_m1_vorlauf_max_c6", 0x27C6, 1, 1, False),
                        ("ONCE", "kessel_maximaltemperatur_06", 0x5706, 1, 1, False),
                    ],
                },
                {
                    "unit_of_measurement": "K",
                    "poll": [
                        ("ONCE", "heizkreis_m1_heizkennlinie_niveau_d4", 0x27D4, 1, 1, True),
                        ("ONCE", "warmwasser_kessel_offset_60", 0x6760, 1, 1, False),
                    ],
                },
                {
                    "unit_of_measurement": "%",
                    "poll": [
                        ("ONCE", "heizkreis_m1_pumpe_max_drehzahl_e6", 0x27E6, 1, 1, False),
                        ("ONCE", "heizkreis_m1_pumpe_min_drehzahl_e7", 0x27E7, 1, 1, False),
                        ("ONCE", "heizkreis_m1_pumpe_reduziert_e9",    0x27E9, 1, 1, False),
                        ("ONCE", "interne_pumpe_solldrehzahl_31",      0x5731, 1, 1, False),
                    ],
                },
                {
                    "unit_of_measurement": "min",
                    "poll": [
                        ("ONCE", "heizkreis_m1_pumpe_reduziert_a9", 0x27A9, 1, 1, False),
                        ("ONCE", "warmwasser_pumpennachlauf_62",     0x6762, 1, 1, False),
                    ],
                },
                {
                    "poll": [
                        ("ONCE", "heizkreis_m1_speichervorrang_a2",         0x27A2, 1, 1, False),
                        ("ONCE", "heizkreis_m1_frostschutz_a4",             0x27A4, 1, 1, False),
                        ("ONCE", "heizkreis_m1_sommerspar_schaltschwelle_a5",0x27A5, 1, 1, False),
                        ("ONCE", "heizkreis_m1_mischersparfunktion_a7",      0x27A7, 1, 1, False),
                        ("ONCE", "heizkreis_m1_heizkennlinie_neigung_d3",    0x27D3, 1, 0.1, False),
                        ("ONCE", "heizkreis_m1_pumpentyp_e5",                0x27E5, 1, 1, False),
                        ("ONCE", "heizkreis_m1_pumpe_nebenbetrieb_e8",       0x27E8, 1, 1, False),
                        ("ONCE", "heizkreis_m1_temperaturprogramm_f1",       0x27F1, 1, 1, False),
                        ("ONCE", "heizkreis_m1_party_zeitbegrenzung_f2",     0x27F2, 1, 1, False),
                        ("ONCE", "interne_pumpe_kennung_30",                 0x5730, 1, 1, False),
                        ("ONCE", "warmwasser_sollbereich_56",                0x6756, 1, 1, False),
                        ("ONCE", "warmwasser_einschalt_offset_59",           0x6759, 1, 1, False),
                        ("ONCE", "warmwasser_speicher_anbindung_5b",         0x675B, 1, 1, False),
                        ("ONCE", "umschaltventil_bauart_65",                 0x6765, 1, 1, False),
                        ("ONCE", "zirkulation_bei_ww_soll1_71",             0x6771, 1, 1, False),
                        ("ONCE", "zirkulation_bei_ww_soll2_72",             0x6772, 1, 1, False),
                        ("ONCE", "relais_k12_funktion_53",                   0x7753, 1, 1, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Coding-plug limits / characteristics - read only
        #
        # Hardware-verified on this exact WB2A / VDensHO1 controller.
        # These are appliance-specific values from the coding plug, not live
        # operating setpoints. No write controls are exposed.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_kesselsoll_max",          0x1050, 16, "b:8:8",   1, False),
                ("ONCE", "codierstecker_kesselsoll_min",          0x1050, 16, "b:9:9",   1, False),
                ("ONCE", "codierstecker_wwsoll_max",              0x1050, 16, "b:10:10", 1, False),
                ("ONCE", "codierstecker_wwsoll_min",              0x1050, 16, "b:11:11", 1, False),
                ("ONCE", "codierstecker_kesseltemperatur_min",    0x1070, 16, "b:0:0",   1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_ww_max_leistung",                  0x1050, 16, "b:12:12", 1, False),
                ("ONCE", "codierstecker_heizung_max_leistung",             0x1050, 16, "b:13:13", 1, False),
                ("ONCE", "codierstecker_brenner_min_leistung",             0x1070, 16, "b:1:1",   1, False),
                ("ONCE", "codierstecker_kesselsollleistung_speicherbetrieb", 0x1070, 16, "b:4:4",   1, False),
                ("ONCE", "codierstecker_interne_pumpe_min_drehzahl",       0x1070, 16, "b:5:5",   1, False),
            ],
        },
        # Additional appliance-type fields from the already verified
        # coding-plug block 0x1050. These are read-only enumerations.
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Umlaufwasserheizer{% elif v == 1 %}Kombiwasserheizer ohne Komfortfunktion{% elif v == 2 %}Kombiwasserheizer mit Komfortfunktion{% elif v == 3 %}Kompaktgerät (Ladespeicher 80 l){% elif v == 4 %}Kompaktgerät mit Solar (Ladespeicher 260 l){% else %}Wert {{ v }}{% endif %}",
            "poll": [
                ("ONCE", "codierstecker_bauart_warmwasser", 0x1050, 16, "b:1:1", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}einstufiger Brenner{% elif v == 1 %}zweistufiger Brenner{% elif v == 2 %}modulierender Brenner{% else %}Wert {{ v }}{% endif %}",
            "poll": [
                ("ONCE", "codierstecker_brennertyp", 0x1050, 16, "b:3:3", 1, False),
            ],
        },

        # Configured appliance limits / diverter-valve type from 0x1030.
        # Hardware-verified raw block:
        # 41 BE 1D E2 03 FC 51 AE 64 9B 00 FF 00 FF 00 FF
        # Known fields are stored with their bytewise complement following:
        #   GWG30 byte 0 = 65 % max DHW power
        #   GWG32 byte 2 = 29 % max heating power
        #   GWG34 byte 4 = 3 = Grundfos diverter valve
        # Only source-documented fields are exposed.
        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_ww_leistungsbegrenzung",      0x1030, 16, "b:0:0", 1, False),
                ("ONCE", "codierstecker_heizung_leistungsbegrenzung", 0x1030, 16, "b:2:2", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}ohne{% elif v == 1 %}Viessmann Umschaltventil{% elif v == 2 %}Wilo Umschaltventil{% elif v == 3 %}Grundfos Umschaltventil{% else %}Wert {{ v }}{% endif %}",
            "poll": [
                ("ONCE", "codierstecker_umschaltventil_bauart", 0x1030, 16, "b:4:4", 1, False),
            ],
        },

        # Boiler/burner regulator parameters from coding plug 0x1060.
        # Hardware-verified raw block:
        # 04 08 1E 04 05 04 1E 14 00 00 00 00 00 00 00 00
        # Keep these 0x1060 entries consecutive; all values are read-only.
        {
            "domain": "sensor",
            "unit_of_measurement": "K",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brenner_einschaltdifferenz",             0x1060, 16, "b:0:0", 1, False),
                ("ONCE", "codierstecker_brenner_ausschaltdifferenz",             0x1060, 16, "b:1:1", 1, False),
                ("ONCE", "codierstecker_brenner_ausschaltdifferenz_volllast",    0x1060, 16, "b:4:4", 1, False),
                ("ONCE", "codierstecker_brenner_pausenabbruch_differenz",        0x1060, 16, "b:6:6", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "%/K",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 1,
            "poll": [
                ("ONCE", "codierstecker_kt_regler_verstaerkung", 0x1060, 16, "b:2:2", 0.1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_kt_regler_nachstellzeit", 0x1060, 16, "b:3:3", 10, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "min",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brenner_mindestpausenzeit", 0x1060, 16, "b:5:5", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brenner_pausenabbruch_temperatur", 0x1060, 16, "b:7:7", 1, False),
            ],
        },

        # DHW / DLH regulator parameters from coding plug 0x1080.
        # Hardware-verified raw block:
        # 04 08 1E 28 37 00 03 08 00 00 00 00 00 00 00 00
        # Source terminology uses "DLH". Depending on the DHW appliance type,
        # not every parameter necessarily participates in active control.
        # Keep all 0x1080 byte filters consecutive so one block read is reused.
        {
            "domain": "sensor",
            "unit_of_measurement": "K",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_dlh_ausschaltdifferenz_start_stop", 0x1080, 16, "b:0:0", 1, False),
                ("ONCE", "codierstecker_dlh_einschaltdifferenz_start_stop", 0x1080, 16, "b:1:1", 1, False),
                ("ONCE", "codierstecker_dlh_ausschaltdifferenz",            0x1080, 16, "b:7:7", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_dlh_nachlaufzeit",           0x1080, 16, "b:2:2", 1, False),
                ("ONCE", "codierstecker_dlh_max_anstiegszeit",       0x1080, 16, "b:3:3", 1, False),
                ("ONCE", "codierstecker_dlh_reglervorhaltezeit",     0x1080, 16, "b:5:5", 10, False),
                ("ONCE", "codierstecker_dlh_reglernachstellzeit",    0x1080, 16, "b:6:6", 10, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "%/K",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 1,
            "poll": [
                ("ONCE", "codierstecker_dlh_reglerverstaerkung", 0x1080, 16, "b:4:4", 0.1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Regelfunktion{% elif v == 1 %}AUS{% elif v == 2 %}EIN{% else %}Wert {{ v }}{% endif %}",
            "poll": [
                ("ONCE", "codierstecker_zirkulationspumpe_bei_speicherladung", 0x1080, 16, "b:8:8", 1, False),
            ],
        },

        # Grundfos diverter-valve motion profile from coding plug 0x10C0.
        # This appliance selects Grundfos via GWG34=3.
        # Hardware-verified raw block:
        # 5A 32 2D C8 5A 32 02 32 02 32 00 FF FF FF FF FF
        # GWGC2/GWGC3 use the VDensHO1 catalog multiplier x2.
        # Frequency values have no documented unit in the source catalog.
        {
            "domain": "sensor",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_grundfos_uv_schrittzahl_x1", 0x10C0, 16, "b:0:0",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_frequenz_x1",    0x10C0, 16, "b:1:1",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_schrittzahl_x2", 0x10C0, 16, "b:2:2",   2, False),
                ("ONCE", "codierstecker_grundfos_uv_frequenz_x2",    0x10C0, 16, "b:3:3",   2, False),
                ("ONCE", "codierstecker_grundfos_uv_schrittzahl_x3", 0x10C0, 16, "b:4:4",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_frequenz_x3",    0x10C0, 16, "b:5:5",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_schrittzahl_x4", 0x10C0, 16, "b:6:6",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_frequenz_x4",    0x10C0, 16, "b:7:7",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_schrittzahl_x5", 0x10C0, 16, "b:8:8",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_frequenz_x5",    0x10C0, 16, "b:9:9",   1, False),
                ("ONCE", "codierstecker_grundfos_uv_position_heizen",0x10C0, 16, "b:10:10", 1, False),
            ],
        },

        # Burner characteristic curve from coding plug 0x1090.
        # GWG91..GWG9A map requested boiler output 10..100 % to the
        # controller's burner modulation value. Hardware-verified raw block:
        # 00 21 21 21 2F 37 3F 48 51 5A 64 00 00 00 00 00
        # Keep these entries consecutive so optolink-splitter reuses one read.
        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brennerkennlinie_10",  0x1090, 16, "b:1:1",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_20",  0x1090, 16, "b:2:2",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_30",  0x1090, 16, "b:3:3",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_40",  0x1090, 16, "b:4:4",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_50",  0x1090, 16, "b:5:5",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_60",  0x1090, 16, "b:6:6",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_70",  0x1090, 16, "b:7:7",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_80",  0x1090, 16, "b:8:8",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_90",  0x1090, 16, "b:9:9",   1, False),
                ("ONCE", "codierstecker_brennerkennlinie_100", 0x1090, 16, "b:10:10", 1, False),
            ],
        },

        {
            "domain": "sensor",
            "unit_of_measurement": "K",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brenner_offset", 0x1070, 16, "b:2:2", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 0,
            "poll": [
                ("ONCE", "codierstecker_brenner_anfahroptimierung", 0x1070, 16, "b:3:3", 10, False),
                ("ONCE", "codierstecker_interne_pumpe_nachlauf",    0x1070, 16, "b:6:6",  1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Internal burner/control-chain diagnostics.
        # Hardware-verified in live burner cycles:
        #   A307 = A391 = effective boiler target on the local heating path
        #   55E0 bytes 1..2  = normal RKR boiler target, little-endian / 10 C
        #   55E0 bytes10..11 = startup-optimized internal RKR target / 10 C.
        #        At restart release it drops exactly 20 K below the normal
        #        target and then ramps back during the startup optimization.
        #   55E0 byte14 bit0 = restart/start release:
        #        0 during the nominal ~240 s post-flame restart inhibition,
        #        1 when restart is released. Observed byte states:
        #        0x00 inhibited, 0x01 released/start phase, 0x43 regulation.
        #   A38F byte0 = 31.5..65.0 %, byte1 = 1 while firing / 0 when off
        #   A393 tracks 0x0810 boiler temperature within normal sequential-read
        #        jitter (mean delta +0.04 K over the captured cycle)
        #   55D3 byte0 closely follows burner modulation during firing, but is
        #        also active during pre-purge; expose only as diagnostic
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 1,
            "poll": [
                ("DIAG", "blr_kesselsolltemperatur_effektiv",  0xA307, 2, 0.01, False),
                ("DIAG", "cfdm_kesselsolltemperatur_effektiv", 0xA391, 2, 0.01, False),
                # nvoSupplyTemp_CFDM; hardware-verified against 0x0810 over a
                # full start/stop cycle. Mean delta was +0.04 K, mean absolute
                # delta 0.14 K (sequential reads, therefore not atomic).
                ("DIAG", "cfdm_vorlauftemperatur",              0xA393, 2, 0.01, False),
                # nviConsumerDmd Temp CFDM; hardware-readable, but verified as
                # an inactive/external input on this WB2A's local heating path:
                # it stayed 0.00 C both idle and during a live 50 C burner run.
                ("DIAG", "cfdm_consumer_demand_temperatur",     0xA385, 2, 0.01, False),
            ],
        },
        # -----------------------------------------------------------------
        # RKR restart inhibition and startup optimization.
        #
        # One FAST raw 0x55E0/17 read feeds all Home Assistant entities below.
        # The derived entities subscribe to that MQTT state topic, so this
        # adds only one Optolink read per FAST cycle.
        #
        # Hardware evidence (two independent controlled cycles):
        #   * byte14 bit0 stayed 0 despite strong thermal demand;
        #   * first new 55DC startup command appeared at ~239.9 / ~241 s;
        #   * byte14 bit0 changed to 1 immediately before startup;
        #   * bytes10..11 changed from normal target to target-20 K at release;
        #   * byte14 changed 0x01 -> 0x43 about 12 s after FLAME_START.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": False,
            "icon": "mdi:code-braces",
            "poll": [
                ("FAST", "rkr_statusblock_55e0_raw", 0x55E0, 17, "raw", False),
            ],
        },
        {
            "domain": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 1,
            "nopoll": [
                {
                    "name": "rkr_kesselsolltemperatur_normal",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "value_template": "{% set s = value | trim %}{% set lo = s[2:4] | int(0, 16) %}{% set hi = s[4:6] | int(0, 16) %}{{ ((lo + 256 * hi) / 10) | round(1) }}",
                },
                {
                    # Preserve the existing entity id/unique_id. This value is
                    # now correctly described as the startup-optimized internal
                    # RKR target rather than a simple mirror of the normal target.
                    "name": "rkr_kesselsolltemperatur",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "value_template": "{% set s = value | trim %}{% set lo = s[20:22] | int(0, 16) %}{% set hi = s[22:24] | int(0, 16) %}{{ ((lo + 256 * hi) / 10) | round(1) }}",
                },
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:state-machine",
            "nopoll": [
                {
                    "name": "rkr_brennerzustand",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "value_template": "{% set s = value | trim %}{% set n = (s[2:4] | int(0, 16)) + 256 * (s[4:6] | int(0, 16)) %}{% set o = (s[20:22] | int(0, 16)) + 256 * (s[22:24] | int(0, 16)) %}{% set b = s[28:30] | int(0, 16) %}{% if b == 0 %}Taktsperre aktiv{% elif b == 1 and o != n %}Brenner-Startphase{% elif b == 1 %}Wiederanlauf freigegeben{% elif b == 67 %}Regelbetrieb{% else %}RKR 0x{{ '%02X' | format(b) }}{% endif %}",
                },
                {
                    "name": "rkr_statusbyte_55e0_b14",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:code-tags",
                    "value_template": "{% set b = (value | trim)[28:30] | int(0, 16) %}0x{{ '%02X' | format(b) }}",
                },
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "1",
            "payload_off": "0",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "nopoll": [
                {
                    "name": "brenner_taktsperre_aktiv",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:timer-lock",
                    "value_template": "{% set b = (value | trim)[28:30] | int(0, 16) %}{{ 1 if (b % 2) == 0 else 0 }}",
                },
                {
                    "name": "brenner_wiederanlauf_freigegeben",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:lock-open-variant",
                    "value_template": "{% set b = (value | trim)[28:30] | int(0, 16) %}{{ 1 if (b % 2) == 1 else 0 }}",
                },
                {
                    "name": "brenner_startphase",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:progress-clock",
                    "value_template": "{% set s = value | trim %}{% set n = (s[2:4] | int(0, 16)) + 256 * (s[4:6] | int(0, 16)) %}{% set o = (s[20:22] | int(0, 16)) + 256 * (s[22:24] | int(0, 16)) %}{% set b = s[28:30] | int(0, 16) %}{{ 1 if b == 1 and o != n else 0 }}",
                },
                {
                    "name": "brenner_anfahroptimierung_aktiv",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:tune-vertical",
                    "value_template": "{% set s = value | trim %}{% set n = (s[2:4] | int(0, 16)) + 256 * (s[4:6] | int(0, 16)) %}{% set o = (s[20:22] | int(0, 16)) + 256 * (s[22:24] | int(0, 16)) %}{{ 1 if o != n else 0 }}",
                },
                {
                    "name": "brenner_regelbetrieb",
                    "state_topic": "{mqtt_base}/rkr_statusblock_55e0_raw",
                    "icon": "mdi:fire",
                    "value_template": "{% set b = (value | trim)[28:30] | int(0, 16) %}{{ 1 if b == 67 else 0 }}",
                },
            ],
        },

        {
            "domain": "sensor",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "suggested_display_precision": 1,
            "poll": [
                ("DIAG", "cfdm_leistungswert", 0xA38F, 2, "b:0:0", 0.5, False),
                # 55D3 byte0 is treated by historical vcontrold/OpenV configs
                # as a fine burner-power value. This WB2A capture confirms a
                # close correlation while firing (69 at A305=66%, 38 at
                # A305=33%), but the field already ramps during pre-purge.
                # Therefore keep it diagnostic and describe it as a GFA
                # power/control value rather than thermal output.
                ("DIAG", "gfa_leistungs_ansteuerwert_fein", 0x55D3, 9, "b:0:0", 1, False),
            ],
        },

        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% set m = {0:'HVAC_AUTO',1:'HVAC_HEAT',2:'HVAC_MRNG_WRMUP',3:'HVAC_COOL',4:'HVAC_NIGHT_PURGE',5:'HVAC_PRE_COOL',6:'HVAC_OFF',7:'HVAC_TEST',8:'HVAC_EMERG_HEAT',9:'HVAC_FAN_ONLY',10:'HVAC_FREE_COOL',100:'HVAC_FLOW_TEMP',110:'HVAC_SLAVE_ACTIVE',111:'HVAC_LOW_FIRE',112:'HVAC_HIGH_FIRE',255:'HVAC_NUL'} %}{{ m.get(v, 'Wert ' ~ v) }}",
            "poll": [
                # Hardware-readable external/LON-style input. It remained
                # FF=HVAC_NUL through a complete local heating burner start.
                ("DIAG", "cfdm_application_mode", 0xA382, 1, 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Internal WB2A diagnostics
        #
        # Hardware-verified on this appliance:
        #   0x0A33 = 00          KM error A1 pump
        #   0x0A35 = 00          KM error internal pump
        #   0x5738 = 00          current GFA error status
        #   0x778B..0x778E       00 01 03 03
        #     EEPROM status      = 0
        #     control SW version = 1.3
        #     I2C EEPROM/GWG flag= 3 (source has no value table; keep raw)
        #   0xA395 = 00 02 50 00
        #     byte2 bit 0x01 hard lock = false
        #     byte2 bit 0x04 error     = false
        #   0xA132 current alarm object ends with error code 00.
        #
        # Numeric error/status fields are kept as text diagnostics instead of
        # guessing undocumented nonzero code meanings.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% else %}Code {{ v }}{% endif %}",
            "poll": [
                ("NORMAL", "km_fehler_pumpe_a1",          0x0A33, 1, 1, False),
                ("NORMAL", "km_fehler_interne_pumpe",     0x0A35, 1, 1, False),
                ("NORMAL", "aktueller_gfa_fehlerstatus",  0x5738, 1, 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% else %}Wert {{ v }}{% endif %}",
            "poll": [
                ("SLOW", "eeprom_status", 0x778B, 4, "b:0:0", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(0) %}{{ v // 256 }}.{{ v % 256 }}",
            "poll": [
                ("ONCE", "regelungssoftware_version", 0x778B, 4, "b:1:2::big", 1, False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "poll": [
                ("SLOW", "i2c_eeprom_gwg_flag", 0x778B, 4, "b:3:3", 1, False),
            ],
        },
        {
            "domain": "binary_sensor",
            "payload_on": "True",
            "payload_off": "False",
            "device_class": "problem",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "poll": [
                ("DIAG", "cfdm_harte_sperre",    0xA395, 4, "b:2:2:0x01", "bool", False),
                ("DIAG", "cfdm_fehler",           0xA395, 4, "b:2:2:0x04", "bool", False),
                # A38F byte1 is the documented CFDM power-state enum:
                # 0=AUS, 1=EIN. Live run: 3f01 while firing, 0000 when off.
                ("DIAG", "cfdm_leistungsstatus", 0xA38F, 2, "b:1:1:0x01", "bool", False),
            ],
        },
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Kein Fehler{% elif v >= 0 %}0x{{ '%02X' | format(v) }}{% else %}unbekannt{% endif %}",
            "poll": [
                ("SLOW", "aktueller_alarm_fehlercode", 0xA132, 29, "b:28:28", 1, False),
            ],
        },

        # -----------------------------------------------------------------
        # Identification/topology - diagnostics
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "units": [
                {
                    "poll": [
                        ("ONCE", "geraete_id",                     0x00F8, 8, "raw"),
                        ("ONCE", "codierstecker_sachnummer",       0x1010, 7, "utf8"),
                        ("ONCE", "codierstecker_kennung",          0x1040, 2, "raw"),
                        ("ONCE", "bedienteil_sw_index",            0x7330, 1, 1, False),
                        ("ONCE", "gfa_kennung",                    0x7650, 1, 1, False),
                        ("ONCE", "anlagenschema",                  0x7700, 1, 1, False),
                        ("ONCE", "anlagentyp",                     0x7701, 1, 1, False),
                        ("ONCE", "bauart_warmwasser",              0x8851, 1, 1, False),
                        ("ONCE", "hydraulische_weiche_vorhanden", 0x7752, 1, 1, False),
                        ("ONCE", "solar_typ",                      0x7754, 1, 1, False),
                    ],
                },
            ],
        },

        # -----------------------------------------------------------------
        # Dashboard aliases for diagnostics.
        #
        # These entities deliberately use fresh unique_ids. Older revisions
        # published the original diagnostic entities disabled-by-default, and
        # Home Assistant keeps that entity-registry state even after discovery
        # changes. The aliases subscribe to the already published MQTT topics,
        # so they add no additional Optolink reads.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "nopoll": [
                {
                    "name": "geraete_id_anzeige",
                    "state_topic": "{mqtt_base}/geraete_id",
                },
                {
                    "name": "codierstecker_sachnummer_anzeige",
                    "state_topic": "{mqtt_base}/codierstecker_sachnummer",
                },
                {
                    "name": "codierstecker_kennung_anzeige",
                    "state_topic": "{mqtt_base}/codierstecker_kennung",
                },
                {
                    "name": "bedienteil_sw_index_anzeige",
                    "state_topic": "{mqtt_base}/bedienteil_sw_index",
                },
                {
                    "name": "gfa_kennung_anzeige",
                    "state_topic": "{mqtt_base}/gfa_kennung",
                },
                {
                    "name": "anlagenschema_anzeige",
                    "state_topic": "{mqtt_base}/anlagenschema",
                },
                {
                    "name": "anlagentyp_anzeige",
                    "state_topic": "{mqtt_base}/anlagentyp",
                },
                {
                    "name": "bauart_warmwasser_anzeige",
                    "state_topic": "{mqtt_base}/bauart_warmwasser",
                },
                {
                    "name": "systemzeit_anzeige",
                    "state_topic": "{mqtt_base}/systemzeit",
                },
                {
                    "name": "fehlerhistorie_01_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_01",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_02_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_02",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_03_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_03",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_04_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_04",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_05_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_05",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_06_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_06",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_07_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_07",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_08_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_08",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_09_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_09",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "fehlerhistorie_10_anzeige",
                    "state_topic": "{mqtt_base}/fehlerhistorie_10",
                    "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_montag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_montag",
                },
                {
                    "name": "warmwasser_zeitprogramm_montag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_montag",
                },
                {
                    "name": "zirkulation_zeitprogramm_montag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_montag",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_dienstag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_dienstag",
                },
                {
                    "name": "warmwasser_zeitprogramm_dienstag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_dienstag",
                },
                {
                    "name": "zirkulation_zeitprogramm_dienstag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_dienstag",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_mittwoch_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_mittwoch",
                },
                {
                    "name": "warmwasser_zeitprogramm_mittwoch_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_mittwoch",
                },
                {
                    "name": "zirkulation_zeitprogramm_mittwoch_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_mittwoch",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_donnerstag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_donnerstag",
                },
                {
                    "name": "warmwasser_zeitprogramm_donnerstag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_donnerstag",
                },
                {
                    "name": "zirkulation_zeitprogramm_donnerstag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_donnerstag",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_freitag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_freitag",
                },
                {
                    "name": "warmwasser_zeitprogramm_freitag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_freitag",
                },
                {
                    "name": "zirkulation_zeitprogramm_freitag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_freitag",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_samstag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_samstag",
                },
                {
                    "name": "warmwasser_zeitprogramm_samstag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_samstag",
                },
                {
                    "name": "zirkulation_zeitprogramm_samstag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_samstag",
                },
                {
                    "name": "heizkreis_m1_zeitprogramm_sonntag_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_zeitprogramm_sonntag",
                },
                {
                    "name": "warmwasser_zeitprogramm_sonntag_anzeige",
                    "state_topic": "{mqtt_base}/warmwasser_zeitprogramm_sonntag",
                },
                {
                    "name": "zirkulation_zeitprogramm_sonntag_anzeige",
                    "state_topic": "{mqtt_base}/zirkulation_zeitprogramm_sonntag",
                },
                {
                    "name": "sensorstatus_aussentemperatur_anzeige",
                    "state_topic": "{mqtt_base}/sensorstatus_aussentemperatur",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "sensorstatus_kesseltemperatur_anzeige",
                    "state_topic": "{mqtt_base}/sensorstatus_kesseltemperatur",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "sensorstatus_sts2_anzeige",
                    "state_topic": "{mqtt_base}/sensorstatus_sts2",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "sensorstatus_vlts_anzeige",
                    "state_topic": "{mqtt_base}/sensorstatus_vlts",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "sensorstatus_raum_m1_anzeige",
                    "state_topic": "{mqtt_base}/sensorstatus_raum_m1",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}OK{% elif v == 1 %}Kurzschluss{% elif v == 2 %}Unterbrechung{% elif v == 3 %}Referenzfehler{% elif v == 4 %}Referenzfehler 0x04{% elif v == 5 %}Sensorstatus 5{% elif v == 6 %}Nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
                {
                    "name": "heizkreis_m1_reglervariante_anzeige",
                    "state_topic": "{mqtt_base}/heizkreis_m1_reglervariante",
                    "value_template": "{% set v = value | int(-1) %}{% if v == 0 %}Konstantregelung{% elif v == 1 %}VT-Soll über LON{% elif v == 2 %}Witterungsgeführt{% elif v == 3 %}Raumregelung{% elif v == 4 %}Estrichprogramm{% elif v == 5 %}Heizkreis nicht vorhanden{% else %}Wert {{ v }}{% endif %}",
                },
            ],
        },

        # -----------------------------------------------------------------
        # System clock
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:clock-outline",
            "poll": [
                ("RARE", "systemzeit", 0x088E, 8, "vdatetime"),
            ],
        },

        # -----------------------------------------------------------------
        # Feuerungsautomat (GFA) fault/event history.
        #
        # This is a separate 20-slot archive from the Vitotronic system
        # history at 0x7507. Each 9-byte slot is:
        #   byte0       GFA code (separate code space; no public code map)
        #   bytes1..8   BCD date/time: YYYY MM DD weekday HH MM SS
        #
        # All 20 slots were hardware-readable on this WB2A. Keep the GFA code
        # as raw hex; in particular, do NOT interpret 0x00 as "no fault".
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:alert-octagon-outline",
            "value_template": "{% set v = value | trim | lower %}{% if v | length == 18 and v[2:18] != 'ffffffffffffffff' %}0x{{ v[0:2] | upper }} @ {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% else %}0x{{ v[0:2] | upper }}{% endif %}",
            "poll": [
                ("RARE", "gfa_fehlerhistorie_01", 0x7590, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_02", 0x7599, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_03", 0x75A2, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_04", 0x75AB, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_05", 0x75B4, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_06", 0x75BD, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_07", 0x75C6, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_08", 0x75CF, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_09", 0x75D8, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_10", 0x75E1, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_11", 0x75EA, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_12", 0x75F3, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_13", 0x75FC, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_14", 0x7605, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_15", 0x760E, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_16", 0x7617, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_17", 0x7620, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_18", 0x7629, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_19", 0x7632, 9, "raw", False),
                ("RARE", "gfa_fehlerhistorie_20", 0x763B, 9, "raw", False),
            ],
        },

        # -----------------------------------------------------------------
        # System fault history.
        #
        # Each 9-byte slot is:
        #   byte0       system fault code
        #   bytes1..8   BCD date/time: YYYY MM DD weekday HH MM SS
        #
        # Keep the complete slot in the MQTT state so Home Assistant can show
        # both the exact fault code and its timestamp. Only mappings recovered
        # from the exact local VDensHO1 Vitosoft resources are translated;
        # unknown codes remain visible as raw hex.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:alert-circle-outline",
            "value_template": "{% set v = value | trim | upper %}{% set c = v[0:2] %}{% set m = {'B7':'Kesselcodierkarte falsch/fehlerhaft','F9':'Fehler Gebläse - Drehzahl nicht erreicht','BC':'Fehler Fernbedienung HK1','BD':'Fehler Fernbedienung HK2'} %}{{ c }}{% if c in m %} · {{ m[c] }}{% endif %}{% if v | length == 18 and v[2:18] != 'FFFFFFFFFFFFFFFF' %} · {{ v[2:6] }}-{{ v[6:8] }}-{{ v[8:10] }} {{ v[12:14] }}:{{ v[14:16] }}:{{ v[16:18] }}{% endif %}",
            "poll": [
                ("RARE", "fehlerhistorie_01", 0x7507, 9, "raw", False),
                ("RARE", "fehlerhistorie_02", 0x7510, 9, "raw", False),
                ("RARE", "fehlerhistorie_03", 0x7519, 9, "raw", False),
                ("RARE", "fehlerhistorie_04", 0x7522, 9, "raw", False),
                ("RARE", "fehlerhistorie_05", 0x752B, 9, "raw", False),
                ("RARE", "fehlerhistorie_06", 0x7534, 9, "raw", False),
                ("RARE", "fehlerhistorie_07", 0x753D, 9, "raw", False),
                ("RARE", "fehlerhistorie_08", 0x7546, 9, "raw", False),
                ("RARE", "fehlerhistorie_09", 0x754F, 9, "raw", False),
                ("RARE", "fehlerhistorie_10", 0x7558, 9, "raw", False),
            ],
        },

        # -----------------------------------------------------------------
        # Time programs - read only in this HA draft.
        # schedvdens is supported by current optolink-splitter.
        # -----------------------------------------------------------------
        {
            "domain": "sensor",
            "entity_category": "diagnostic",
            "enabled_by_default": True,
            "icon": "mdi:calendar-clock",
            "poll": [
                ("ONCE", "heizkreis_m1_zeitprogramm_montag",     0x2000, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_dienstag",   0x2008, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_mittwoch",   0x2010, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_donnerstag", 0x2018, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_freitag",    0x2020, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_samstag",    0x2028, 8, "schedvdens"),
                ("ONCE", "heizkreis_m1_zeitprogramm_sonntag",    0x2030, 8, "schedvdens"),

                ("ONCE", "warmwasser_zeitprogramm_montag",       0x2100, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_dienstag",     0x2108, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_mittwoch",     0x2110, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_donnerstag",   0x2118, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_freitag",      0x2120, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_samstag",      0x2128, 8, "schedvdens"),
                ("ONCE", "warmwasser_zeitprogramm_sonntag",      0x2130, 8, "schedvdens"),

                ("ONCE", "zirkulation_zeitprogramm_montag",      0x2200, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_dienstag",    0x2208, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_mittwoch",    0x2210, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_donnerstag",  0x2218, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_freitag",     0x2220, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_samstag",     0x2228, 8, "schedvdens"),
                ("ONCE", "zirkulation_zeitprogramm_sonntag",     0x2230, 8, "schedvdens"),
            ],
        },
    ],
}

# Intentionally omitted from this live HA profile:
#
# * 0x2302 as writable economy switch:
#     hardware write ACK is ignored by the controller.
#
# * M2, solar, hydraulic-separator values:
#     hardware/configuration proves these options are absent.
#
# * 0x081A VTS/VLTS, 0x0814 STS2, 0x0896 room temperature:
#     corresponding sensor-status datapoints report invalid/open/reference
#     states; their 20.0 C values are defaults, not physical measurements.
#
# * Fan speed:
#     0x0B1C / 0x0B1E return P300 error on this SW03 controller.
#
# * Burner reset/unlock:
#     no defensible ordinary VDensHO1 P300 write datapoint is known.
#
# * Water-heater/climate aggregate entities:
#     intentionally deferred until their mode semantics are tested as a unit.
#
# * Select write coverage:
#     Full exact-catalog enums are exposed. Hardware write tests on this exact
#     appliance currently cover 0x2323 values 2/4 and 0x6773 values 0/7.
#
# * Direct circulation "boost" abstraction:
#     0x6773 R/W is verified, but the physical 0->7 forcing effect from an
#     actually OFF baseline is still an open test.
